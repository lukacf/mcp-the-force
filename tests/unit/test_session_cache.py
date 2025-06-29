"""Test session cache with async operations."""

import pytest
import tempfile
import os
import asyncio

from mcp_second_brain.session_cache import _SQLiteSessionCache, session_cache


@pytest.mark.asyncio
async def test_basic_set_get():
    """Test basic set and get operations."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteSessionCache(db_path=db_path, ttl=3600)

        # Set a response ID
        await cache.set_response_id("test_session", "test_response")

        # Get it back
        result = await cache.get_response_id("test_session")
        assert result == "test_response"

        # Non-existent session returns None
        result = await cache.get_response_id("nonexistent")
        assert result is None

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_persistence():
    """Test that data persists across cache instances."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        # First instance
        cache1 = _SQLiteSessionCache(db_path=db_path, ttl=3600)
        await cache1.set_response_id("persist_test", "persist_value")
        cache1.close()

        # Second instance should see the data
        cache2 = _SQLiteSessionCache(db_path=db_path, ttl=3600)
        result = await cache2.get_response_id("persist_test")
        assert result == "persist_value"
        cache2.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_expiration():
    """Test TTL expiration."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteSessionCache(db_path=db_path, ttl=1)

        await cache.set_response_id("expire_test", "expire_value")

        # Should exist immediately
        result = await cache.get_response_id("expire_test")
        assert result == "expire_value"

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache.get_response_id("expire_test")
        assert result is None

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_concurrent_access():
    """Test concurrent operations work correctly."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteSessionCache(db_path=db_path, ttl=3600)

        async def write_many(prefix, count):
            for i in range(count):
                await cache.set_response_id(f"{prefix}_{i}", f"value_{i}")

        async def read_many(prefix, count):
            results = []
            for i in range(count):
                result = await cache.get_response_id(f"{prefix}_{i}")
                results.append(result)
            return results

        # Write concurrently
        await asyncio.gather(
            write_many("group1", 5),
            write_many("group2", 5),
            write_many("group3", 5),
        )

        # Read concurrently
        results = await asyncio.gather(
            read_many("group1", 5),
            read_many("group2", 5),
            read_many("group3", 5),
        )

        # Verify all reads succeeded
        for group_results in results:
            assert all(r is not None for r in group_results)

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_long_ids_rejected():
    """Test that overly long IDs are rejected."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteSessionCache(db_path=db_path, ttl=3600)

        # Session ID too long
        with pytest.raises(ValueError, match="session_id too long"):
            await cache.set_response_id("x" * 1025, "value")

        with pytest.raises(ValueError, match="session_id too long"):
            await cache.get_response_id("x" * 1025)

        # Response ID too long
        with pytest.raises(ValueError, match="response_id too long"):
            await cache.set_response_id("session", "x" * 1025)

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_proxy_interface():
    """Test the global proxy interface."""
    # The session_cache proxy should work with await
    await session_cache.set_response_id("proxy_test", "proxy_value")
    result = await session_cache.get_response_id("proxy_test")
    assert result == "proxy_value"

    # Close should work
    session_cache.close()
