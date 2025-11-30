"""Unified session cache for all providers using LiteLLM's message format."""

import time
import orjson
import logging
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from mcp_the_force.config import get_settings
from mcp_the_force.sqlite_base_cache import BaseSQLiteCache

logger = logging.getLogger(__name__)


@dataclass
class UnifiedSession:
    """Represents a cached session with unified history and provider metadata.

    History format depends on the API being used:
    - Chat Completions API: [{"role": "user", "content": "...", "tool_calls": [...]}]
    - Responses API: [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "..."}]}]

    Provider metadata can include:
    - response_id: For OpenAI Responses API continuation
    - api_format: "chat" or "responses" to track which format is being used
    - deployment_id: For LiteLLM router deployments
    """

    project: str
    tool: str
    session_id: str
    updated_at: int
    history: List[Dict[str, Any]] = field(default_factory=list)
    provider_metadata: Dict[str, Any] = field(default_factory=dict)


class _SQLiteUnifiedSessionCache(BaseSQLiteCache):
    """SQLite-backed unified session cache for all providers."""

    def __init__(self, db_path: str, ttl: int):
        # New schema with composite key
        create_table_sql = """CREATE TABLE IF NOT EXISTS unified_sessions(
            project             TEXT NOT NULL,
            tool                TEXT NOT NULL,
            session_id          TEXT NOT NULL,
            history             TEXT,
            provider_metadata   TEXT,
            updated_at          INTEGER NOT NULL,
            PRIMARY KEY (project, tool, session_id)
        )"""

        # Migration: check if old schema exists and migrate if needed
        self._migrate_if_needed(db_path)
        super().__init__(
            db_path=db_path,
            ttl=ttl,
            table_name="unified_sessions",
            create_table_sql=create_table_sql,
            purge_probability=get_settings().session_cleanup_probability,
        )

        # Create the session_summaries table
        self._create_summaries_table()

    def _migrate_if_needed(self, db_path: str):
        """Check if old schema exists and migrate to new schema if needed."""
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # Check if table exists and get its schema
            cursor.execute("PRAGMA table_info(unified_sessions)")
            columns = cursor.fetchall()

            if columns:
                # Check if we have the old schema (no project/tool columns)
                column_names = [col[1] for col in columns]
                if "project" not in column_names and "tool" not in column_names:
                    logger.info("Migrating unified_sessions table to new schema")

                    # Create new table with new schema
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS unified_sessions_new(
                            project             TEXT NOT NULL,
                            tool                TEXT NOT NULL,
                            session_id          TEXT NOT NULL,
                            history             TEXT,
                            provider_metadata   TEXT,
                            updated_at          INTEGER NOT NULL,
                            PRIMARY KEY (project, tool, session_id)
                        )
                    """)

                    # Migrate existing data with default values
                    cursor.execute("""
                        INSERT INTO unified_sessions_new (project, tool, session_id, history, provider_metadata, updated_at)
                        SELECT 'default', 'unknown', session_id, history, provider_metadata, updated_at
                        FROM unified_sessions
                    """)

                    # Drop old table and rename new one
                    cursor.execute("DROP TABLE unified_sessions")
                    cursor.execute(
                        "ALTER TABLE unified_sessions_new RENAME TO unified_sessions"
                    )

                    conn.commit()
                    logger.info("Migration completed successfully")
        finally:
            conn.close()

    def _create_summaries_table(self):
        """Create the session_summaries table for caching summaries."""
        if self._conn is None:
            raise RuntimeError("Database connection is not initialized")

        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS session_summaries (
                    project TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (project, tool, session_id)
                )
            """)

    async def get_session(
        self, project: str, tool: str, session_id: str
    ) -> Optional[UnifiedSession]:
        """
        Retrieves a complete session (history and metadata) from the database.
        Returns None if the session is not found or is expired.
        """
        self._validate_session_id(session_id)
        now = int(time.time())

        rows = await self._execute_async(
            "SELECT history, provider_metadata, updated_at FROM unified_sessions WHERE project = ? AND tool = ? AND session_id = ?",
            (project, tool, session_id),
        )

        if not rows:
            logger.debug(f"No session found for {session_id}")
            return None

        history_json, metadata_json, updated_at = rows[0]

        # Check if expired
        if now - updated_at >= self.ttl:
            await self.delete_session(project, tool, session_id)
            logger.debug(f"Session {session_id} expired")
            return None

        # Parse JSON data
        history = orjson.loads(history_json) if history_json else []
        metadata = orjson.loads(metadata_json) if metadata_json else {}

        return UnifiedSession(
            project=project,
            tool=tool,
            session_id=session_id,
            updated_at=updated_at,
            history=history,
            provider_metadata=metadata,
        )

    async def set_session(self, session: UnifiedSession):
        """
        Saves a UnifiedSession object to the database, overwriting any
        existing entry with the same session_id.
        """
        self._validate_session_id(session.session_id)
        now = int(time.time())

        # Invalidate any cached summary when session is updated
        await self._execute_async(
            "DELETE FROM session_summaries WHERE project = ? AND tool = ? AND session_id = ?",
            (session.project, session.tool, session.session_id),
            fetch=False,
        )

        # Serialize to JSON
        history_json = (
            orjson.dumps(session.history).decode("utf-8") if session.history else None
        )
        metadata_json = (
            orjson.dumps(session.provider_metadata).decode("utf-8")
            if session.provider_metadata
            else None
        )

        await self._execute_async(
            "REPLACE INTO unified_sessions(project, tool, session_id, history, provider_metadata, updated_at) VALUES(?,?,?,?,?,?)",
            (
                session.project,
                session.tool,
                session.session_id,
                history_json,
                metadata_json,
                now,
            ),
            fetch=False,
        )

        logger.debug(f"Saved session {session.session_id}")
        await self._probabilistic_cleanup()

    async def delete_session(self, project: str, tool: str, session_id: str):
        """Explicitly deletes a session from the cache."""
        await self._execute_async(
            "DELETE FROM unified_sessions WHERE project = ? AND tool = ? AND session_id = ?",
            (project, tool, session_id),
            fetch=False,
        )

    async def get_summary(
        self, project: str, tool: str, session_id: str
    ) -> Optional[str]:
        """Get cached summary for a session."""
        rows = await self._execute_async(
            "SELECT summary FROM session_summaries WHERE project = ? AND tool = ? AND session_id = ?",
            (project, tool, session_id),
        )
        return rows[0][0] if rows else None

    async def set_summary(
        self, project: str, tool: str, session_id: str, summary: str
    ) -> None:
        """Set cached summary for a session."""
        await self._execute_async(
            """
            REPLACE INTO session_summaries (project, tool, session_id, summary, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project, tool, session_id, summary, int(time.time())),
            fetch=False,
        )


# Singleton pattern
_instance: Optional[_SQLiteUnifiedSessionCache] = None
_instance_lock = threading.Lock()


def _get_instance() -> _SQLiteUnifiedSessionCache:
    """Get or create the singleton cache instance."""
    global _instance
    with _instance_lock:
        if _instance is None:
            settings = get_settings()
            db_path = settings.session_db_path
            ttl = settings.session_ttl_seconds
            try:
                _instance = _SQLiteUnifiedSessionCache(db_path=db_path, ttl=ttl)
                logger.info(f"Initialized unified session cache at {db_path}")
            except Exception as exc:
                logger.critical(f"Failed to initialize unified session cache: {exc}")
                raise RuntimeError(
                    f"Could not initialize unified session cache: {exc}"
                ) from exc
        return _instance


class UnifiedSessionCache:
    """Public proxy for the unified session cache with convenience methods."""

    @staticmethod
    async def get_session(
        project: str, tool: str, session_id: str
    ) -> Optional[UnifiedSession]:
        """Get complete session data."""
        return await _get_instance().get_session(project, tool, session_id)

    @staticmethod
    async def set_session(session: UnifiedSession) -> None:
        """Save complete session data."""
        await _get_instance().set_session(session)

    @staticmethod
    async def delete_session(project: str, tool: str, session_id: str) -> None:
        """Delete a session."""
        await _get_instance().delete_session(project, tool, session_id)

    @staticmethod
    async def get_summary(project: str, tool: str, session_id: str) -> Optional[str]:
        """Get cached summary for a session."""
        return await _get_instance().get_summary(project, tool, session_id)

    @staticmethod
    async def set_summary(
        project: str, tool: str, session_id: str, summary: str
    ) -> None:
        """Set cached summary for a session."""
        await _get_instance().set_summary(project, tool, session_id, summary)

    # Convenience methods for history
    @staticmethod
    async def get_history(
        project: str, tool: str, session_id: str
    ) -> List[Dict[str, Any]]:
        """Get conversation history in LiteLLM format."""
        session = await _get_instance().get_session(project, tool, session_id)
        return session.history if session else []

    @staticmethod
    async def set_history(
        project: str, tool: str, session_id: str, history: List[Dict[str, Any]]
    ) -> None:
        """Update conversation history, preserving metadata."""
        session = await _get_instance().get_session(project, tool, session_id)
        if not session:
            session = UnifiedSession(
                project=project,
                tool=tool,
                session_id=session_id,
                updated_at=int(time.time()),
            )

        session.history = history
        await _get_instance().set_session(session)

    @staticmethod
    async def append_message(
        project: str, tool: str, session_id: str, message: Dict[str, Any]
    ) -> None:
        """Append a complete message to history (preserves all fields).

        For Chat Completions API:
            {"role": "user", "content": "Hello", "name": "John", ...}

        For Responses API:
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hello"}]}
        """
        session = await _get_instance().get_session(project, tool, session_id)
        if not session:
            session = UnifiedSession(
                project=project,
                tool=tool,
                session_id=session_id,
                updated_at=int(time.time()),
            )

        session.history.append(message)
        await _get_instance().set_session(session)

    @staticmethod
    async def append_chat_message(
        project: str, tool: str, session_id: str, role: str, content: str, **kwargs
    ) -> None:
        """Convenience method to append a Chat Completions API message."""
        message = {"role": role, "content": content, **kwargs}
        await UnifiedSessionCache.append_message(project, tool, session_id, message)

    @staticmethod
    async def append_responses_message(
        project: str, tool: str, session_id: str, role: str, text: str
    ) -> None:
        """Convenience method to append a Responses API text message."""
        message = {
            "type": "message",
            "role": role,
            "content": [
                {
                    "type": "text",  # Responses API uses "text" for all text content
                    "text": text,
                }
            ],
        }
        await UnifiedSessionCache.append_message(project, tool, session_id, message)

    # Convenience methods for OpenAI response_id
    @staticmethod
    async def get_response_id(
        project: str, tool: str, session_id: str
    ) -> Optional[str]:
        """Get OpenAI response_id from metadata."""
        session = await _get_instance().get_session(project, tool, session_id)
        if session:
            return session.provider_metadata.get("response_id")
        return None

    @staticmethod
    async def set_response_id(
        project: str, tool: str, session_id: str, response_id: str
    ) -> None:
        """Set OpenAI response_id in metadata, preserving history."""
        session = await _get_instance().get_session(project, tool, session_id)
        if not session:
            session = UnifiedSession(
                project=project,
                tool=tool,
                session_id=session_id,
                updated_at=int(time.time()),
            )

        session.provider_metadata["response_id"] = response_id
        await _get_instance().set_session(session)

    # Methods for Responses API format
    @staticmethod
    async def append_function_call(
        project: str,
        tool: str,
        session_id: str,
        name: str,
        arguments: str,
        call_id: str,
    ) -> None:
        """Append a Responses API function call."""
        item = {
            "type": "function_call",
            "name": name,
            "arguments": arguments,
            "call_id": call_id,
        }
        await UnifiedSessionCache.append_message(project, tool, session_id, item)

    @staticmethod
    async def append_function_output(
        project: str, tool: str, session_id: str, call_id: str, output: str
    ) -> None:
        """Append a Responses API function output."""
        item = {"type": "function_call_output", "call_id": call_id, "output": output}
        await UnifiedSessionCache.append_message(project, tool, session_id, item)

    # Convenience method for provider metadata
    @staticmethod
    async def get_metadata(project: str, tool: str, session_id: str, key: str) -> Any:
        """Get specific metadata value."""
        session = await _get_instance().get_session(project, tool, session_id)
        if session:
            return session.provider_metadata.get(key)
        return None

    @staticmethod
    async def set_metadata(
        project: str, tool: str, session_id: str, key: str, value: Any
    ) -> None:
        """Set specific metadata value, preserving other data."""
        session = await _get_instance().get_session(project, tool, session_id)
        if not session:
            session = UnifiedSession(
                project=project,
                tool=tool,
                session_id=session_id,
                updated_at=int(time.time()),
            )

        session.provider_metadata[key] = value
        await _get_instance().set_session(session)

    @staticmethod
    async def get_api_format(project: str, tool: str, session_id: str) -> Optional[str]:
        """Get the API format being used ('chat' or 'responses')."""
        result = await UnifiedSessionCache.get_metadata(
            project, tool, session_id, "api_format"
        )
        return str(result) if result is not None else None

    @staticmethod
    async def set_api_format(
        project: str, tool: str, session_id: str, api_format: str
    ) -> None:
        """Set the API format being used."""
        await UnifiedSessionCache.set_metadata(
            project, tool, session_id, "api_format", api_format
        )

    @staticmethod
    def close() -> None:
        """Close the cache and clean up resources."""
        global _instance
        with _instance_lock:
            if _instance is not None:
                _instance.close()
                _instance = None


# Global instance for convenience
unified_session_cache = UnifiedSessionCache()
