import os
import tempfile
import pytest
from google.genai import types

from mcp_the_force.gemini_session_cache import (
    _SQLiteGeminiSessionCache,
    _content_to_dict,
    _dict_to_content,
)


@pytest.mark.asyncio
async def test_basic_store_and_retrieve():
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name
    try:
        cache = _SQLiteGeminiSessionCache(db_path=db_path, ttl=3600)
        await cache.append_exchange("session1", "hello", "hi")
        msgs = await cache.get_messages("session1")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_expiration(monkeypatch):
    from tests.conftest import mock_clock

    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name
    try:
        cache = _SQLiteGeminiSessionCache(db_path=db_path, ttl=1)

        with mock_clock(monkeypatch) as tick:
            await cache.append_exchange("s", "u", "a")

            # Should exist immediately
            messages = await cache.get_messages("s")
            assert len(messages) == 2

            # Advance virtual clock past TTL
            tick(1.1)

            # Should be expired
            assert await cache.get_messages("s") == []

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_corrupted_json_handling():
    """Test that corrupted JSON in database is handled gracefully."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name
    try:
        cache = _SQLiteGeminiSessionCache(db_path=db_path, ttl=3600)

        # Get the actual database path the cache is using (may be different in CI due to MCP_ADAPTER_MOCK)
        real_db_path = cache.db_path

        # Ensure table exists by doing a dummy operation first
        await cache.get_messages("dummy")

        # Manually insert corrupted JSON using the cache's actual database path
        import sqlite3
        import time

        conn = sqlite3.connect(real_db_path)
        conn.execute(
            "INSERT INTO gemini_sessions (session_id, messages, updated_at) VALUES (?, ?, ?)",
            ("corrupted", "{invalid json", int(time.time())),
        )
        conn.commit()
        conn.close()

        # Should return empty list instead of crashing
        messages = await cache.get_messages("corrupted")
        assert messages == []

        cache.close()
    finally:
        os.unlink(db_path)


# === NEW SERIALIZATION TESTS ===


class TestGeminiSerialization:
    """Test serialization and deserialization of Gemini Content objects."""

    def test_serialize_simple_text_content(self):
        """Test serialization of simple text content."""
        content = types.Content(
            role="user", parts=[types.Part.from_text(text="Hello, how are you?")]
        )

        serialized = _content_to_dict(content)
        expected = {"role": "user", "parts": [{"text": "Hello, how are you?"}]}

        assert serialized == expected

    def test_deserialize_simple_text_content(self):
        """Test deserialization of simple text content."""
        data = {"role": "assistant", "parts": [{"text": "I'm doing well, thank you!"}]}

        content = _dict_to_content(data)

        assert content.role == "assistant"
        assert len(content.parts) == 1
        assert content.parts[0].text == "I'm doing well, thank you!"

    def test_serialize_function_call(self):
        """Test serialization of function call content."""
        function_call = types.FunctionCall(
            name="search_project_history",
            args={"query": "Python programming", "max_results": 10},
        )
        content = types.Content(
            role="assistant", parts=[types.Part(function_call=function_call)]
        )

        serialized = _content_to_dict(content)
        expected = {
            "role": "assistant",
            "parts": [
                {
                    "function_call": {
                        "name": "search_project_history",
                        "args": {"query": "Python programming", "max_results": 10},
                    }
                }
            ],
        }

        assert serialized == expected

    def test_deserialize_function_call(self):
        """Test deserialization of function call content."""
        data = {
            "role": "assistant",
            "parts": [
                {
                    "function_call": {
                        "name": "search_task_files",
                        "args": {"query": "test", "max_results": 20},
                    }
                }
            ],
        }

        content = _dict_to_content(data)

        assert content.role == "assistant"
        assert len(content.parts) == 1
        part = content.parts[0]
        assert hasattr(part, "function_call")
        assert part.function_call.name == "search_task_files"
        assert part.function_call.args["query"] == "test"
        assert part.function_call.args["max_results"] == 20

    def test_roundtrip_serialization(self):
        """Test that serialization and deserialization are inverses."""
        original_content = types.Content(
            role="assistant",
            parts=[
                types.Part.from_text(text="I'll help you with that."),
                types.Part(
                    function_call=types.FunctionCall(
                        name="search_task_files",
                        args={"query": "neural networks", "max_results": 15},
                    )
                ),
            ],
        )

        # Serialize then deserialize
        serialized = _content_to_dict(original_content)
        deserialized = _dict_to_content(serialized)

        # Check that we get back the same structure
        assert deserialized.role == original_content.role
        assert len(deserialized.parts) == len(original_content.parts)

        # Check text part
        assert deserialized.parts[0].text == original_content.parts[0].text

        # Check function call part
        orig_fc = original_content.parts[1].function_call
        deser_fc = deserialized.parts[1].function_call
        assert deser_fc.name == orig_fc.name
        assert deser_fc.args == orig_fc.args
