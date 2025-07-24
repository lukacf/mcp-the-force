"""Test concurrent access to session caches."""

import asyncio
import pytest
import tempfile
import os
from typing import List

from mcp_the_force.session_cache import _SQLiteSessionCache
from mcp_the_force.gemini_session_cache import _SQLiteGeminiSessionCache


@pytest.mark.asyncio
async def test_openai_session_concurrent_access():
    """Test concurrent read/write operations on OpenAI session cache."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteSessionCache(db_path=db_path, ttl=3600)

        async def write_session(session_id: str, response_id: str):
            """Write a session entry."""
            await cache.set_response_id(session_id, response_id)

        async def read_session(session_id: str) -> str:
            """Read a session entry."""
            return await cache.get_response_id(session_id)

        # Create 8 concurrent tasks (mix of reads and writes)
        tasks = []

        # Write operations
        for i in range(4):
            task = write_session(f"session_{i}", f"response_{i}")
            tasks.append(task)

        # Run writes first
        await asyncio.gather(*tasks)

        # Now do concurrent reads and writes
        tasks = []
        for i in range(4):
            # Read existing
            task = read_session(f"session_{i}")
            tasks.append(task)
            # Write new
            task = write_session(f"session_new_{i}", f"response_new_{i}")
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Verify reads returned correct values
        for i in range(0, 8, 2):
            session_idx = i // 2
            assert results[i] == f"response_{session_idx}"

        # Verify new writes succeeded
        for i in range(4):
            result = await cache.get_response_id(f"session_new_{i}")
            assert result == f"response_new_{i}"

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_gemini_session_concurrent_access():
    """Test concurrent read/write operations on Gemini session cache."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteGeminiSessionCache(db_path=db_path, ttl=3600)

        async def append_messages(session_id: str, idx: int):
            """Append messages to a session."""
            await cache.append_exchange(
                session_id, f"User message {idx}", f"Assistant response {idx}"
            )

        async def read_messages(session_id: str) -> List:
            """Read messages from a session."""
            return await cache.get_messages(session_id)

        # Create sessions first
        init_tasks = []
        for i in range(4):
            task = append_messages(f"session_{i}", 0)
            init_tasks.append(task)
        await asyncio.gather(*init_tasks)

        # Now do concurrent operations
        tasks = []

        # Mix of reads and appends
        for i in range(4):
            # Read existing session
            task = read_messages(f"session_{i}")
            tasks.append(task)
            # Append to existing session
            task = append_messages(f"session_{i}", i + 1)
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Verify initial reads had 2 messages (1 exchange)
        for i in range(0, 8, 2):
            messages = results[i]
            assert len(messages) == 2
            assert messages[0]["role"] == "user"
            assert messages[1]["role"] == "assistant"

        # Verify appends succeeded
        for i in range(4):
            messages = await cache.get_messages(f"session_{i}")
            # Should have 4 messages now (2 exchanges)
            assert len(messages) == 4

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_high_concurrency_stress():
    """Stress test with higher concurrency level."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteSessionCache(db_path=db_path, ttl=3600)

        async def stress_operation(idx: int):
            """Perform multiple operations."""
            session_id = f"stress_{idx % 10}"  # Reuse some sessions
            response_id = f"response_{idx}"

            # Write
            await cache.set_response_id(session_id, response_id)
            # Read
            result = await cache.get_response_id(session_id)
            # Write again with different value
            await cache.set_response_id(session_id, f"{response_id}_updated")

            return result

        # Run 20 concurrent operations
        tasks = [stress_operation(i) for i in range(20)]
        results = await asyncio.gather(*tasks)

        # All operations should complete without errors
        assert len(results) == 20
        # At least some reads should have found values
        assert any(r is not None for r in results)

        cache.close()
    finally:
        os.unlink(db_path)
