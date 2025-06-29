import time
import json
import logging
from typing import List, Dict
import os
import tempfile

from mcp_second_brain.config import get_settings
from mcp_second_brain.sqlite_base_cache import BaseSQLiteCache

logger = logging.getLogger(__name__)

_settings = get_settings()
_DEFAULT_TTL = _settings.session_ttl_seconds
_DB_PATH = _settings.session_db_path
_PURGE_PROB = _settings.session_cleanup_probability


class _SQLiteGeminiSessionCache(BaseSQLiteCache):
    """SQLite-backed store for Gemini conversation history."""

    def __init__(self, db_path: str = _DB_PATH, ttl: int = _DEFAULT_TTL):
        if os.getenv("MCP_ADAPTER_MOCK") == "1" and db_path == _DB_PATH:
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
            purge_probability=_PURGE_PROB,
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


try:
    _instance = _SQLiteGeminiSessionCache()
    logger.info(f"Initialized Gemini session cache at {_DB_PATH}")
except Exception as exc:
    logger.critical(f"Failed to initialize Gemini session cache: {exc}")
    raise RuntimeError(f"Could not initialize Gemini session cache: {exc}") from exc


class GeminiSessionCache:
    """Proxy class that maintains the async interface."""

    @staticmethod
    async def get_messages(session_id: str) -> List[Dict[str, str]]:
        return await _instance.get_messages(session_id)

    @staticmethod
    async def append_exchange(
        session_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        await _instance.append_exchange(session_id, user_msg, assistant_msg)

    @staticmethod
    def close() -> None:
        return _instance.close()


# Global instance for convenience
gemini_session_cache = GeminiSessionCache()
