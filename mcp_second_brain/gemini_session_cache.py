import time
import orjson
import logging
import threading
from typing import List, Dict, Optional, Any
import os
import tempfile
from google.genai import types

from mcp_second_brain.config import get_settings
from mcp_second_brain.sqlite_base_cache import BaseSQLiteCache

logger = logging.getLogger(__name__)

# Configuration will be read lazily to support test isolation


# --- Serialization Helpers ---
def _content_to_dict(content: types.Content) -> Dict[str, Any]:
    """Serialize a Gemini Content object to a JSON-compatible dictionary."""
    parts_list = []
    if content.parts is not None:
        for part in content.parts:
            part_dict = {}
            # Use getattr to safely access optional attributes
            if text := getattr(part, "text", None):
                part_dict["text"] = text
            if fc := getattr(part, "function_call", None):
                part_dict["function_call"] = {"name": fc.name, "args": dict(fc.args)}
            if fr := getattr(part, "function_response", None):
                part_dict["function_response"] = {
                    "name": fr.name,
                    "response": fr.response,
                }
            if part_dict:
                parts_list.append(part_dict)
    return {"role": getattr(content, "role", "user"), "parts": parts_list}


def _dict_to_content(data: Dict[str, Any]) -> types.Content:
    """Deserialize a dictionary back into a Gemini Content object."""
    parts = []
    for part_data in data.get("parts", []):
        if "text" in part_data:
            parts.append(types.Part.from_text(text=part_data["text"]))
        elif "function_call" in part_data:
            fc_data = part_data["function_call"]
            parts.append(
                types.Part(
                    function_call=types.FunctionCall(
                        name=fc_data["name"], args=fc_data["args"]
                    )
                )
            )
        elif "function_response" in part_data:
            fr_data = part_data["function_response"]
            parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fr_data["name"], response=fr_data["response"]
                    )
                )
            )
    return types.Content(role=data.get("role"), parts=parts)


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

    async def get_history(self, session_id: str) -> List[types.Content]:
        """Retrieve full conversation history for a session."""
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
            history_data = orjson.loads(messages_json)
            return [_dict_to_content(item) for item in history_data]
        except Exception:
            logger.warning("Failed to decode history for %s", session_id)
            return []

    async def set_history(self, session_id: str, history: List[types.Content]):
        """Save the entire conversation history for a session."""
        self._validate_session_id(session_id)
        now = int(time.time())

        # Serialize the entire history
        history_data = [_content_to_dict(content) for content in history]
        history_json = orjson.dumps(history_data).decode("utf-8")

        await self._execute_async(
            "REPLACE INTO gemini_sessions(session_id, messages, updated_at) VALUES(?,?,?)",
            (session_id, history_json, now),
            fetch=False,
        )
        await self._probabilistic_cleanup()

    # Deprecated methods for backward compatibility
    async def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        """Deprecated: Use get_history instead."""
        logger.warning("get_messages is deprecated, use get_history instead")
        history = await self.get_history(session_id)
        # Convert back to old format for compatibility
        messages = []
        for content in history:
            if content.parts is not None:
                for part in content.parts:
                    if hasattr(part, "text") and part.text:
                        messages.append(
                            {"role": str(content.role), "content": str(part.text)}
                        )
        return messages

    async def append_exchange(
        self, session_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        """Deprecated: Use set_history instead."""
        logger.warning("append_exchange is deprecated, use set_history instead")
        # Get existing history
        history = await self.get_history(session_id)
        # Add new messages
        history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_msg)])
        )
        history.append(
            types.Content(
                role="assistant", parts=[types.Part.from_text(text=assistant_msg)]
            )
        )
        # Save updated history
        await self.set_history(session_id, history)


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
    async def get_history(session_id: str) -> List[types.Content]:
        return await _get_instance().get_history(session_id)

    @staticmethod
    async def set_history(session_id: str, history: List[types.Content]) -> None:
        await _get_instance().set_history(session_id, history)

    # Backward compatibility methods
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
