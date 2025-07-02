import time
import json
import logging
import threading
from typing import List, Dict, Optional
import os
import tempfile

from mcp_second_brain.config import get_settings
from mcp_second_brain.sqlite_base_cache import BaseSQLiteCache

logger = logging.getLogger(__name__)

# Configuration will be read lazily to support test isolation


class _SQLiteGeminiSessionCache(BaseSQLiteCache):
    """SQLite-backed store for Gemini conversation history."""

    def __init__(self, db_path: str, ttl: int):
        if os.getenv("MCP_ADAPTER_MOCK") == "1":
            tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
            db_path = tmp.name
            tmp.close()

        create_table_sql = """CREATE TABLE IF NOT EXISTS gemini_sessions(
            session_id  TEXT PRIMARY KEY,
            messages    TEXT NOT NULL,
            updated_at  INTEGER NOT NULL
        )"""
        super().__init__(
            db_path=db_path,
            ttl=ttl,
            table_name="gemini_sessions",
            create_table_sql=create_table_sql,
            purge_probability=get_settings().session_cleanup_probability,
        )

    async def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        """Retrieve conversation messages for a session."""
        self._validate_session_id(session_id)

        now = int(time.time())

        rows = await self._execute_async(
            "SELECT messages, updated_at FROM gemini_sessions WHERE session_id = ?",
            (session_id,),
        )

        if not rows:
            return []

        messages_json, updated_at = rows[0]
        if now - updated_at >= self.ttl:
            await self._execute_async(
                "DELETE FROM gemini_sessions WHERE session_id = ?",
                (session_id,),
                fetch=False,
            )
            return []

        try:
            messages: List[Dict[str, str]] = json.loads(messages_json)
            return messages
        except Exception:
            logger.warning("Failed to decode messages for %s", session_id)
            return []

    async def append_exchange(
        self, session_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        """Append a user/assistant exchange to a session."""
        self._validate_session_id(session_id)

        now = int(time.time())

        # Get existing messages
        rows = await self._execute_async(
            "SELECT messages FROM gemini_sessions WHERE session_id = ?",
            (session_id,),
        )

        if rows:
            try:
                messages = json.loads(rows[0][0])
            except Exception:
                messages = []
        else:
            messages = []

        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": assistant_msg})

        await self._execute_async(
            "REPLACE INTO gemini_sessions(session_id, messages, updated_at) VALUES(?,?,?)",
            (session_id, json.dumps(messages), now),
            fetch=False,
        )

        # Probabilistic cleanup
        await self._probabilistic_cleanup()


# Use lazy initialization to support test isolation
_instance: Optional[_SQLiteGeminiSessionCache] = None
_instance_lock = threading.Lock()


def _get_instance() -> _SQLiteGeminiSessionCache:
    global _instance
    with _instance_lock:
        if _instance is None:
            # Re-read settings to get current DB path
            settings = get_settings()
            db_path = settings.session_db_path
            ttl = settings.session_ttl_seconds
            try:
                _instance = _SQLiteGeminiSessionCache(db_path=db_path, ttl=ttl)
                logger.info(f"Initialized Gemini session cache at {db_path}")
            except Exception as exc:
                logger.critical(f"Failed to initialize Gemini session cache: {exc}")
                raise RuntimeError(
                    f"Could not initialize Gemini session cache: {exc}"
                ) from exc
        return _instance


class GeminiSessionCache:
    """Proxy class that maintains the async interface."""

    @staticmethod
    async def get_messages(session_id: str) -> List[Dict[str, str]]:
        result = await _get_instance().get_messages(session_id)
        return result

    @staticmethod
    async def append_exchange(
        session_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        await _get_instance().append_exchange(session_id, user_msg, assistant_msg)

    @staticmethod
    def close() -> None:
        global _instance
        with _instance_lock:
            if _instance is not None:
                _instance.close()
                _instance = None


# Global instance for convenience
gemini_session_cache = GeminiSessionCache()
