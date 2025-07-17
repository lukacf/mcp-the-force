#!/usr/bin/env python3
"""
Loiter Killer Service - Manages OpenAI vector stores and files lifecycle.
"""

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from openai import AsyncOpenAI
from pydantic import BaseModel
from typing import List
import asyncio
import sqlite3
import os
import time
import uvicorn
import logging
import sys
import uuid


def setup_logging():
    """Initialize VictoriaLogs-based logging for Loiter Killer."""
    logger = logging.getLogger("loiter_killer")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.hasHandlers():
        logger.handlers.clear()

    # Generate instance ID for this service (commented out for now)
    # session_id = str(uuid.uuid4())[:8]
    # instance_id = f"loiter-killer_container_{session_id}"  # Not used currently

    # Skip VictoriaLogs for now - it's causing issues with Docker networking
    # try:
    #     # Connect to VictoriaLogs container via Docker Compose network
    #     loki_handler = LokiHandler(
    #         url="http://victorialogs:9428/insert/loki/api/v1/push?_stream_fields=app,instance_id",
    #         tags={
    #             "app": "loiter-killer",
    #             "instance_id": instance_id,
    #             "project": os.getenv("MCP_PROJECT_PATH", "/app"),
    #         },
    #         version="1",
    #     )
    #     logger.addHandler(loki_handler)
    # except Exception as e:
    #     print(f"Warning: Could not connect to VictoriaLogs: {e}", file=sys.stderr)

    # Also add stderr handler for debugging
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(stderr_handler)

    logger.info("Loiter Killer logging initialized")
    return logger


# Initialize logging
logger = setup_logging()


# Response models
class AcquireResponse(BaseModel):
    vector_store_id: str
    reused: bool
    files: List[str]  # Deprecated - kept for backward compatibility
    file_paths: List[str]  # List of file paths in the vector store


class TrackFilesRequest(BaseModel):
    file_paths: List[str]  # List of file paths to track


class TrackFilesResponse(BaseModel):
    tracked: int


class RenewResponse(BaseModel):
    status: str


class CleanupResponse(BaseModel):
    cleaned: int


# Database setup
def init_db():
    """Initialize SQLite database."""
    conn = sqlite3.connect("loiter_killer.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            vector_store_id TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)
    # New schema: track by file path, not file ID
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_paths (
            session_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            PRIMARY KEY (session_id, file_path)
        )
    """)
    # Migrate from old schema if needed
    cursor = conn.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='files'
    """)
    if cursor.fetchone():
        # Old table exists, migrate data
        conn.execute("""
            INSERT OR IGNORE INTO file_paths (session_id, file_path)
            SELECT session_id, file_path FROM files
        """)
        conn.execute("DROP TABLE files")
    conn.commit()
    return conn


# Global state (will be initialized in lifespan)
db = None
client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global db, client

    # Initialize database
    db = init_db()

    # Initialize OpenAI client
    if os.getenv("TEST_MODE") == "true":
        # In test mode, create a mock client
        from unittest.mock import AsyncMock, Mock

        client = AsyncMock()
        client.vector_stores = AsyncMock()
        client.vector_stores.create = AsyncMock(
            return_value=Mock(id=f"vs_test_{int(time.time())}")
        )
        client.files = AsyncMock()
        client.files.delete = AsyncMock()
        client.vector_stores.delete = AsyncMock()
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable is required")
            logger.error("Please set it before starting the service:")
            logger.error("  export OPENAI_API_KEY=your-api-key")
            raise ValueError("OPENAI_API_KEY environment variable is required")
        client = AsyncOpenAI(api_key=api_key)

    # Start background cleanup task
    cleanup_task = asyncio.create_task(background_cleanup())

    yield

    # Stop background task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Cleanup
    if db:
        db.close()


async def background_cleanup():
    """Background task to clean up expired sessions."""
    while True:
        try:
            await asyncio.sleep(300)  # Check every 5 minutes
            await cleanup_expired_sessions()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Background cleanup error: {e}")


# Create FastAPI app
app = FastAPI(title="Loiter Killer Service", lifespan=lifespan)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/session/{session_id}/acquire", response_model=AcquireResponse)
async def acquire_session(session_id: str):
    """Acquire or create a vector store for a session."""
    logger.info(f"Acquire request for session {session_id}")

    # Check if session exists
    cursor = db.execute(
        "SELECT vector_store_id FROM sessions WHERE session_id = ?", (session_id,)
    )
    row = cursor.fetchone()

    if row:
        # Update expiration
        expires_at = int(time.time()) + 3600  # 1 hour from now
        db.execute(
            "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
            (expires_at, session_id),
        )
        db.commit()

        # Get file paths
        cursor = db.execute(
            "SELECT file_path FROM file_paths WHERE session_id = ?", (session_id,)
        )
        file_paths = [row[0] for row in cursor.fetchall()]

        logger.info(
            f"Reusing existing vector store {row[0]} for session {session_id} with {len(file_paths)} files"
        )

        return AcquireResponse(
            vector_store_id=row[0],
            reused=True,
            files=[],  # Deprecated
            file_paths=file_paths,
        )

    # Create new vector store
    logger.info(f"Creating new vector store for session {session_id}")
    vector_store = await client.vector_stores.create(
        name=f"session_{session_id[:8]}",
        expires_after={"anchor": "last_active_at", "days": 7},
    )

    # Save to database
    expires_at = int(time.time()) + 3600  # 1 hour from now
    db.execute(
        "INSERT INTO sessions (session_id, vector_store_id, expires_at) VALUES (?, ?, ?)",
        (session_id, vector_store.id, expires_at),
    )
    db.commit()

    logger.info(f"Created new vector store {vector_store.id} for session {session_id}")

    return AcquireResponse(
        vector_store_id=vector_store.id, reused=False, files=[], file_paths=[]
    )


@app.post("/session/{session_id}/files", response_model=TrackFilesResponse)
async def track_files(session_id: str, request: TrackFilesRequest):
    """Track files for a session."""
    # Verify session exists
    cursor = db.execute(
        "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Session not found")

    # Track file paths
    tracked = 0
    for file_path in request.file_paths:
        try:
            db.execute(
                "INSERT INTO file_paths (session_id, file_path) VALUES (?, ?)",
                (session_id, file_path),
            )
            tracked += 1
        except sqlite3.IntegrityError:
            # File path already tracked for this session
            pass

    db.commit()

    # Update session expiration
    expires_at = int(time.time()) + 3600  # 1 hour from now
    db.execute(
        "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
        (expires_at, session_id),
    )
    db.commit()

    return TrackFilesResponse(tracked=tracked)


@app.post("/session/{session_id}/renew", response_model=RenewResponse)
async def renew_lease(session_id: str):
    """Renew the lease for a session."""
    # Check if session exists
    cursor = db.execute(
        "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Session not found")

    # Update expiration
    expires_at = int(time.time()) + 3600  # 1 hour from now
    db.execute(
        "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
        (expires_at, session_id),
    )
    db.commit()

    return RenewResponse(status="renewed")


async def cleanup_expired_sessions():
    """Clean up expired sessions and their resources."""
    global db, client

    # Find expired sessions
    cutoff = int(time.time())
    cursor = db.execute(
        "SELECT session_id, vector_store_id FROM sessions WHERE expires_at < ?",
        (cutoff,),
    )
    expired_sessions = cursor.fetchall()

    cleaned = 0
    for session_id, vector_store_id in expired_sessions:
        try:
            # Note: We can't delete individual files anymore since we don't track file IDs
            # The files will be deleted when the vector store is deleted

            # Delete vector store (this will also delete its files)
            if os.getenv("TEST_MODE") == "true":
                logger.info(f"TEST MODE: Would delete vector store {vector_store_id}")
            else:
                try:
                    await client.vector_stores.delete(vector_store_id)
                    logger.info(f"Deleted vector store {vector_store_id} and its files")
                except Exception as e:
                    logger.error(
                        f"Failed to delete vector store {vector_store_id}: {e}"
                    )

            # Clean up database
            db.execute("DELETE FROM file_paths WHERE session_id = ?", (session_id,))
            db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            db.commit()

            cleaned += 1

        except Exception as e:
            logger.error(f"Error cleaning session {session_id}: {e}")

    return cleaned


@app.post("/cleanup", response_model=CleanupResponse)
async def trigger_cleanup():
    """Manually trigger cleanup of expired sessions."""
    cleaned = await cleanup_expired_sessions()
    return CleanupResponse(cleaned=cleaned)


if __name__ == "__main__":
    # Run the service (bind to 0.0.0.0 in container)
    uvicorn.run(app, host="0.0.0.0", port=9876)
