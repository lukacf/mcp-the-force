import sqlite3
import time
import random
import threading
import json
import logging
from typing import List, Dict

from mcp_second_brain.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_DEFAULT_TTL = _settings.session_ttl_seconds
_DB_PATH = _settings.session_db_path
_PURGE_PROB = _settings.session_cleanup_probability


class _SQLiteGeminiSessionCache:
    """SQLite-backed store for Gemini conversation history."""

    def __init__(self, db_path: str = _DB_PATH, ttl: int = _DEFAULT_TTL):
        self.db_path = db_path
        self.ttl = ttl
        self._lock = threading.RLock()

        try:
            self._conn = sqlite3.connect(
                db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False
            )
            self._init_db()
            logger.info(f"Gemini session cache using SQLite at {db_path}")
        except sqlite3.Error as e:
            raise RuntimeError(f"SQLite init failed: {e}") from e

    def _init_db(self):
        with self._conn:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                PRAGMA busy_timeout=5000;

                CREATE TABLE IF NOT EXISTS gemini_sessions(
                    session_id  TEXT PRIMARY KEY,
                    messages    TEXT NOT NULL,
                    updated_at  INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_gemini_sessions_updated
                  ON gemini_sessions(updated_at);
                """
            )

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        """Retrieve conversation messages for a session."""
        if len(session_id) > 1024:
            raise ValueError("session_id too long")

        now = int(time.time())

        with self._lock, self._conn:
            cur = self._conn.execute(
                "SELECT messages, updated_at FROM gemini_sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()

            if not row:
                return []

            messages_json, updated_at = row
            if now - updated_at >= self.ttl:
                self._conn.execute(
                    "DELETE FROM gemini_sessions WHERE session_id = ?", (session_id,)
                )
                return []

            try:
                return json.loads(messages_json)
            except Exception:
                logger.warning("Failed to decode messages for %s", session_id)
                return []

    def append_exchange(
        self, session_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        """Append a user/assistant exchange to a session."""
        if len(session_id) > 1024:
            raise ValueError("session_id too long")

        now = int(time.time())

        with self._lock, self._conn:
            cur = self._conn.execute(
                "SELECT messages FROM gemini_sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            if row:
                try:
                    messages = json.loads(row[0])
                except Exception:
                    messages = []
            else:
                messages = []

            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": assistant_msg})

            self._conn.execute(
                "REPLACE INTO gemini_sessions(session_id, messages, updated_at) VALUES(?,?,?)",
                (session_id, json.dumps(messages), now),
            )

            if random.random() < _PURGE_PROB:
                cutoff = now - self.ttl
                self._conn.execute(
                    "DELETE FROM gemini_sessions WHERE updated_at < ?", (cutoff,)
                )

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


try:
    _instance = _SQLiteGeminiSessionCache()
    logger.info(f"Initialized Gemini session cache at {_DB_PATH}")
except Exception as exc:
    logger.critical(f"Failed to initialize Gemini session cache: {exc}")
    raise RuntimeError(f"Could not initialize Gemini session cache: {exc}") from exc


class GeminiSessionCache:
    @staticmethod
    def get_messages(session_id: str) -> List[Dict[str, str]]:
        return _instance.get_messages(session_id)

    @staticmethod
    def append_exchange(session_id: str, user_msg: str, assistant_msg: str) -> None:
        return _instance.append_exchange(session_id, user_msg, assistant_msg)

    @staticmethod
    def close() -> None:
        return _instance.close()


# Global instance for convenience
gemini_session_cache = GeminiSessionCache()
