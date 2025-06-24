"""Session cache for OpenAI response ID management."""

import os
import sqlite3
import time
import random
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration from environment
_DEFAULT_TTL = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
_DB_PATH = os.getenv("SESSION_DB_PATH", ".mcp_sessions.sqlite3")
_PURGE_PROB = float(os.getenv("SESSION_CLEANUP_PROBABILITY", "0.01"))


class _SQLiteSessionCache:
    """SQLite-backed session cache for persistent storage."""

    def __init__(self, db_path: str = _DB_PATH, ttl: int = _DEFAULT_TTL):
        self.db_path = db_path
        self.ttl = ttl
        self._lock = threading.RLock()

        try:
            # check_same_thread=False allows other threads to reuse connection
            self._conn = sqlite3.connect(
                db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False
            )
            self._init_db()
            logger.info(f"Session cache using SQLite at {db_path}")
        except sqlite3.Error as e:
            raise RuntimeError(f"SQLite init failed: {e}") from e

    def _init_db(self):
        """Initialize database schema and settings."""
        with self._conn:
            self._conn.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                PRAGMA busy_timeout=5000;
                
                CREATE TABLE IF NOT EXISTS sessions(
                    session_id  TEXT PRIMARY KEY,
                    response_id TEXT NOT NULL,
                    updated_at  INTEGER NOT NULL
                );
                
                CREATE INDEX IF NOT EXISTS idx_sessions_updated 
                ON sessions(updated_at);
            """)

    def get_response_id(self, session_id: str) -> Optional[str]:
        """Get the previous response ID for a session."""
        if len(session_id) > 1024:
            raise ValueError("session_id too long")

        now = int(time.time())

        with self._lock, self._conn:
            cur = self._conn.execute(
                "SELECT response_id, updated_at FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()

            if not row:
                return None

            response_id, updated_at = str(row[0]), row[1]

            # Check if expired
            if now - updated_at >= self.ttl:
                self._conn.execute(
                    "DELETE FROM sessions WHERE session_id = ?", (session_id,)
                )
                return None

            return response_id

    def set_response_id(self, session_id: str, response_id: str):
        """Store a response ID for a session."""
        if len(session_id) > 1024 or len(response_id) > 1024:
            raise ValueError("session_id or response_id too long")

        now = int(time.time())

        with self._lock, self._conn:
            self._conn.execute(
                "REPLACE INTO sessions(session_id, response_id, updated_at) VALUES(?, ?, ?)",
                (session_id, response_id, now),
            )
            logger.debug(f"Stored response_id for session {session_id}")

            # Probabilistic cleanup
            if random.random() < _PURGE_PROB:
                cutoff = now - self.ttl
                self._conn.execute(
                    "DELETE FROM sessions WHERE updated_at < ?", (cutoff,)
                )
                logger.debug("Performed probabilistic session cleanup")

    def close(self):
        """Close database connection."""
        try:
            self._conn.close()
        except Exception:
            pass


class _InMemorySessionCache:
    """Original in-memory implementation as fallback."""

    def __init__(self, ttl=_DEFAULT_TTL):
        self._data = {}
        self.ttl = ttl
        self._lock = threading.RLock()

    def get_response_id(self, session_id: str) -> Optional[str]:
        """Get the previous response ID for a session."""
        self._gc()
        with self._lock:
            session = self._data.get(session_id)
            if session and time.time() - session["updated"] < self.ttl:
                response_id = session.get("response_id")
                return str(response_id) if response_id is not None else None
        return None

    def set_response_id(self, session_id: str, response_id: str):
        """Store a response ID for a session."""
        with self._lock:
            self._data[session_id] = {
                "response_id": response_id,
                "updated": time.time(),
            }
        logger.debug(f"Stored response_id for session {session_id} (in-memory)")

    def _gc(self):
        """Garbage collect expired sessions."""
        now = time.time()
        expired = []
        with self._lock:
            for sid, data in self._data.items():
                if now - data["updated"] >= self.ttl:
                    expired.append(sid)

            for sid in expired:
                del self._data[sid]
                logger.debug(f"Expired session {sid}")

    def close(self):
        """No-op for in-memory cache."""
        pass


# Factory pattern - SQLite is required for persistent session state
try:
    _instance = _SQLiteSessionCache()
    logger.info(f"Successfully initialized SQLite session cache at {_DB_PATH}")
except Exception as exc:
    # Log a critical error and re-raise
    logger.critical(f"Failed to initialize persistent SQLite session cache: {exc}")
    raise RuntimeError(f"Could not initialize session cache: {exc}") from exc


class SessionCache:
    """Proxy class that maintains the original interface."""

    @staticmethod
    def get_response_id(session_id: str) -> Optional[str]:
        return _instance.get_response_id(session_id)

    @staticmethod
    def set_response_id(session_id: str, response_id: str):
        return _instance.set_response_id(session_id, response_id)

    @staticmethod
    def close():
        return _instance.close()


# Global session cache instance for backward compatibility
session_cache = SessionCache()
