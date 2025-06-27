import os
import tempfile
import time

from mcp_second_brain.gemini_session_cache import _SQLiteGeminiSessionCache


def test_basic_store_and_retrieve():
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name
    try:
        cache = _SQLiteGeminiSessionCache(db_path=db_path, ttl=3600)
        cache.append_exchange("session1", "hello", "hi")
        msgs = cache.get_messages("session1")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        cache.close()
    finally:
        os.unlink(db_path)


def test_expiration():
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name
    try:
        cache = _SQLiteGeminiSessionCache(db_path=db_path, ttl=1)
        cache.append_exchange("s", "u", "a")
        time.sleep(1.1)
        assert cache.get_messages("s") == []
        cache.close()
    finally:
        os.unlink(db_path)
