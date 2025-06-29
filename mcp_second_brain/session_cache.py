"""Session cache for OpenAI response ID management."""

import time
import logging
import threading
from typing import Optional

from mcp_second_brain.config import get_settings
from mcp_second_brain.sqlite_base_cache import BaseSQLiteCache

logger = logging.getLogger(__name__)

# Get configuration from centralized settings
_settings = get_settings()
_DEFAULT_TTL = _settings.session_ttl_seconds
_DB_PATH = _settings.session_db_path
_PURGE_PROB = _settings.session_cleanup_probability


class _SQLiteSessionCache(BaseSQLiteCache):
    """SQLite-backed session cache for persistent storage."""

    def __init__(self, db_path: str = _DB_PATH, ttl: int = _DEFAULT_TTL):
        create_table_sql = """CREATE TABLE IF NOT EXISTS sessions(
            session_id  TEXT PRIMARY KEY,
            response_id TEXT NOT NULL,
            updated_at  INTEGER NOT NULL
        )"""
        super().__init__(
            db_path=db_path,
            ttl=ttl,
            table_name="sessions",
            create_table_sql=create_table_sql,
            purge_probability=_PURGE_PROB,
        )

    async def get_response_id(self, session_id: str) -> Optional[str]:
        """Get the previous response ID for a session."""
        self._validate_session_id(session_id)

        now = int(time.time())

        rows = await self._execute_async(
            "SELECT response_id, updated_at FROM sessions WHERE session_id = ?",
            (session_id,),
        )

        if not rows:
            logger.info(f"No previous response found for session {session_id}")
            return None

        response_id, updated_at = str(rows[0][0]), rows[0][1]

        # Check if expired
        if now - updated_at >= self.ttl:
            await self._execute_async(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,), fetch=False
            )
            return None

        logger.info(f"Retrieved response_id {response_id} for session {session_id}")
        return response_id

    async def set_response_id(self, session_id: str, response_id: str):
        """Store a response ID for a session."""
        self._validate_session_id(session_id)
        if len(response_id) > 1024:
            raise ValueError("response_id too long")

        now = int(time.time())

        await self._execute_async(
            "REPLACE INTO sessions(session_id, response_id, updated_at) VALUES(?, ?, ?)",
            (session_id, response_id, now),
            fetch=False,
        )
        logger.info(f"Stored response_id {response_id} for session {session_id}")

        # Probabilistic cleanup
        await self._probabilistic_cleanup()


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
    """Proxy class that maintains the async interface."""

    @staticmethod
    async def get_response_id(session_id: str) -> Optional[str]:
        """Get response ID asynchronously."""
        return await _instance.get_response_id(session_id)

    @staticmethod
    async def set_response_id(session_id: str, response_id: str) -> None:
        """Set response ID asynchronously."""
        await _instance.set_response_id(session_id, response_id)

    @staticmethod
    def close():
        return _instance.close()


# Global session cache instance for backward compatibility
session_cache = SessionCache()
