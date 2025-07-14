import time
import orjson
import logging
import threading
from typing import List, Dict, Optional, Any

from mcp_second_brain.config import get_settings
from mcp_second_brain.sqlite_base_cache import BaseSQLiteCache

logger = logging.getLogger(__name__)


class _SQLiteGrokSessionCache(BaseSQLiteCache):
    """SQLite-backed store for Grok conversation history."""

    def __init__(self, db_path: str, ttl: int):
        create_table_sql = """CREATE TABLE IF NOT EXISTS grok_sessions(
            session_id  TEXT PRIMARY KEY,
            history     TEXT NOT NULL,
            updated_at  INTEGER NOT NULL
        )"""
        super().__init__(
            db_path=db_path,
            ttl=ttl,
            table_name="grok_sessions",
            create_table_sql=create_table_sql,
            purge_probability=get_settings().session_cleanup_probability,
        )

    async def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        self._validate_session_id(session_id)
        now = int(time.time())
        rows = await self._execute_async(
            "SELECT history, updated_at FROM grok_sessions WHERE session_id = ?",
            (session_id,),
        )
        if not rows:
            return []
        history_json, updated_at = rows[0]
        if now - updated_at >= self.ttl:
            await self._execute_async(
                "DELETE FROM grok_sessions WHERE session_id = ?",
                (session_id,),
                fetch=False,
            )
            return []
        return orjson.loads(history_json)  # type: ignore[no-any-return]

    async def set_history(self, session_id: str, history: List[Dict[str, Any]]):
        self._validate_session_id(session_id)
        now = int(time.time())
        await self._execute_async(
            "REPLACE INTO grok_sessions(session_id, history, updated_at) VALUES(?,?,?)",
            (session_id, orjson.dumps(history).decode("utf-8"), now),
            fetch=False,
        )
        await self._probabilistic_cleanup()


# Singleton logic
_instance: Optional[_SQLiteGrokSessionCache] = None
_instance_lock = threading.Lock()


def _get_instance() -> _SQLiteGrokSessionCache:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                settings = get_settings()
                _instance = _SQLiteGrokSessionCache(
                    db_path=settings.session_db_path, ttl=settings.session_ttl_seconds
                )
    return _instance


class GrokSessionCache:
    @staticmethod
    async def get_history(session_id: str) -> List[Dict[str, Any]]:
        return await _get_instance().get_history(session_id)

    @staticmethod
    async def set_history(session_id: str, history: List[Dict[str, Any]]):
        await _get_instance().set_history(session_id, history)

    @staticmethod
    def close() -> None:
        global _instance
        with _instance_lock:
            if _instance is not None:
                _instance.close()
                _instance = None


grok_session_cache = GrokSessionCache()
