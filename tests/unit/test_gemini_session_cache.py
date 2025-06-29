import os
import tempfile
import pytest
import asyncio

from mcp_second_brain.gemini_session_cache import _SQLiteGeminiSessionCache


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
async def test_expiration():
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name
    try:
        cache = _SQLiteGeminiSessionCache(db_path=db_path, ttl=1)
        await cache.append_exchange("s", "u", "a")
        await asyncio.sleep(1.1)
        assert await cache.get_messages("s") == []
        cache.close()
    finally:
        os.unlink(db_path)
