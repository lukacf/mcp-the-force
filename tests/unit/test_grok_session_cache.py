"""Unit tests for Grok session cache functionality."""

import asyncio
import json
import pytest
import tempfile
import os
from unittest.mock import patch

from mcp_second_brain.grok_session_cache import (
    _SQLiteGrokSessionCache,
    GrokSessionCache,
    grok_session_cache,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp:
        db_path = tmp.name
    yield db_path
    try:
        os.unlink(db_path)
    except FileNotFoundError:
        pass


@pytest.fixture
def grok_cache(temp_db):
    """Create a Grok session cache instance for testing."""
    return _SQLiteGrokSessionCache(db_path=temp_db, ttl=3600)


class TestSQLiteGrokSessionCache:
    """Test the internal SQLite Grok session cache implementation."""

    @pytest.mark.asyncio
    async def test_empty_history(self, grok_cache):
        """Test retrieving history for non-existent session."""
        history = await grok_cache.get_history("non-existent-session")
        assert history == []

    @pytest.mark.asyncio
    async def test_store_and_retrieve_basic_history(self, grok_cache):
        """Test storing and retrieving basic conversation history."""
        session_id = "test-session-1"
        test_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        # Store history
        await grok_cache.set_history(session_id, test_history)

        # Retrieve history
        retrieved_history = await grok_cache.get_history(session_id)
        assert retrieved_history == test_history

    @pytest.mark.asyncio
    async def test_store_and_retrieve_tool_calls(self, grok_cache):
        """Test storing and retrieving history with tool calls."""
        session_id = "test-session-tools"
        test_history = [
            {"role": "user", "content": "Search for information about Python"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "search_project_memory",
                            "arguments": '{"query": "Python", "max_results": 10}',
                        },
                    }
                ],
            },
            {
                "tool_call_id": "call_123",
                "role": "tool",
                "name": "search_project_memory",
                "content": "Found 5 results about Python programming...",
            },
            {
                "role": "assistant",
                "content": "Based on the search results, here's what I found about Python...",
            },
        ]

        # Store history
        await grok_cache.set_history(session_id, test_history)

        # Retrieve history
        retrieved_history = await grok_cache.get_history(session_id)
        assert retrieved_history == test_history

    @pytest.mark.asyncio
    async def test_update_existing_history(self, grok_cache):
        """Test updating existing session history."""
        session_id = "test-session-update"
        initial_history = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "First response"},
        ]

        # Store initial history
        await grok_cache.set_history(session_id, initial_history)

        # Update with additional messages
        updated_history = initial_history + [
            {"role": "user", "content": "Second message"},
            {"role": "assistant", "content": "Second response"},
        ]
        await grok_cache.set_history(session_id, updated_history)

        # Retrieve and verify
        retrieved_history = await grok_cache.get_history(session_id)
        assert retrieved_history == updated_history
        assert len(retrieved_history) == 4

    @pytest.mark.asyncio
    async def test_session_ttl_expiration(self, temp_db, monkeypatch):
        """Test that sessions expire based on TTL."""
        from tests.conftest import mock_clock

        # Create cache with very short TTL
        short_ttl_cache = _SQLiteGrokSessionCache(db_path=temp_db, ttl=1)

        session_id = "test-session-ttl"
        test_history = [
            {"role": "user", "content": "Test message"},
            {"role": "assistant", "content": "Test response"},
        ]

        with mock_clock(monkeypatch) as tick:
            # Store history
            await short_ttl_cache.set_history(session_id, test_history)

            # Retrieve immediately (should work)
            retrieved_history = await short_ttl_cache.get_history(session_id)
            assert retrieved_history == test_history

            # Advance virtual clock past TTL
            tick(2)

            # Retrieve after TTL (should be empty)
            expired_history = await short_ttl_cache.get_history(session_id)
            assert expired_history == []

    @pytest.mark.asyncio
    async def test_multiple_sessions(self, grok_cache):
        """Test managing multiple independent sessions."""
        session1_id = "session-1"
        session2_id = "session-2"

        history1 = [
            {"role": "user", "content": "Session 1 message"},
            {"role": "assistant", "content": "Session 1 response"},
        ]

        history2 = [
            {"role": "user", "content": "Session 2 message"},
            {"role": "assistant", "content": "Session 2 response"},
        ]

        # Store both sessions
        await grok_cache.set_history(session1_id, history1)
        await grok_cache.set_history(session2_id, history2)

        # Retrieve and verify independence
        retrieved1 = await grok_cache.get_history(session1_id)
        retrieved2 = await grok_cache.get_history(session2_id)

        assert retrieved1 == history1
        assert retrieved2 == history2
        assert retrieved1 != retrieved2

    @pytest.mark.asyncio
    async def test_invalid_session_id(self, grok_cache):
        """Test handling of invalid session IDs."""
        # Test overly long session ID
        long_session_id = "x" * 1025  # Over the 1024 limit
        with pytest.raises(ValueError, match="session_id too long"):
            await grok_cache.get_history(long_session_id)

        with pytest.raises(ValueError, match="session_id too long"):
            await grok_cache.set_history(long_session_id, [])

    @pytest.mark.asyncio
    async def test_json_serialization_edge_cases(self, grok_cache):
        """Test JSON serialization of complex message structures."""
        session_id = "test-session-complex"

        # Complex history with nested data
        complex_history = [
            {"role": "user", "content": "Complex query"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_complex",
                        "type": "function",
                        "function": {
                            "name": "search_task_files",
                            "arguments": json.dumps(
                                {
                                    "query": "test with \"quotes\" and 'apostrophes'",
                                    "max_results": 20,
                                    "metadata": {"nested": {"key": "value"}},
                                }
                            ),
                        },
                    }
                ],
            },
            {
                "tool_call_id": "call_complex",
                "role": "tool",
                "name": "search_task_files",
                "content": json.dumps(
                    {
                        "results": [
                            {
                                "title": "Result 1",
                                "content": "Content with unicode: 你好",
                            },
                            {
                                "title": "Result 2",
                                "content": "Content with symbols: @#$%^&*()",
                            },
                        ]
                    }
                ),
            },
        ]

        # Store and retrieve
        await grok_cache.set_history(session_id, complex_history)
        retrieved_history = await grok_cache.get_history(session_id)

        assert retrieved_history == complex_history


class TestGrokSessionCacheProxy:
    """Test the GrokSessionCache proxy class."""

    @pytest.mark.asyncio
    async def test_proxy_methods(self, temp_db):
        """Test that proxy methods work correctly."""
        # Mock the singleton to use our test database
        with patch(
            "mcp_second_brain.grok_session_cache._get_instance"
        ) as mock_get_instance:
            test_cache = _SQLiteGrokSessionCache(db_path=temp_db, ttl=3600)
            mock_get_instance.return_value = test_cache

            session_id = "proxy-test-session"
            test_history = [
                {"role": "user", "content": "Proxy test"},
                {"role": "assistant", "content": "Proxy response"},
            ]

            # Test through proxy
            await GrokSessionCache.set_history(session_id, test_history)
            retrieved_history = await GrokSessionCache.get_history(session_id)

            assert retrieved_history == test_history

    @pytest.mark.asyncio
    async def test_global_instance(self):
        """Test that global instance is accessible."""
        # This test just verifies the global instance exists and has the expected methods
        assert hasattr(grok_session_cache, "get_history")
        assert hasattr(grok_session_cache, "set_history")
        assert callable(grok_session_cache.get_history)
        assert callable(grok_session_cache.set_history)


class TestGrokSessionCacheIntegration:
    """Integration tests for Grok session cache with realistic scenarios."""

    @pytest.mark.asyncio
    async def test_realistic_conversation_flow(self, grok_cache):
        """Test a realistic conversation flow with multiple turns and tool calls."""
        session_id = "realistic-conversation"

        # Start conversation
        history = [
            {"role": "user", "content": "Can you help me understand the codebase?"}
        ]
        await grok_cache.set_history(session_id, history)

        # Assistant responds with tool call
        history.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_search_1",
                        "type": "function",
                        "function": {
                            "name": "search_project_memory",
                            "arguments": '{"query": "codebase overview", "max_results": 5}',
                        },
                    }
                ],
            }
        )
        await grok_cache.set_history(session_id, history)

        # Tool response
        history.extend(
            [
                {
                    "tool_call_id": "call_search_1",
                    "role": "tool",
                    "name": "search_project_memory",
                    "content": "Found documentation about MCP Second-Brain server architecture...",
                },
                {
                    "role": "assistant",
                    "content": "Based on the project memory, this is an MCP server that provides access to multiple AI models...",
                },
            ]
        )
        await grok_cache.set_history(session_id, history)

        # User follow-up
        history.append(
            {
                "role": "user",
                "content": "What about the specific implementation of the Grok adapter?",
            }
        )
        await grok_cache.set_history(session_id, history)

        # Verify final state
        final_history = await grok_cache.get_history(session_id)
        assert len(final_history) == 5
        assert (
            final_history[-1]["content"]
            == "What about the specific implementation of the Grok adapter?"
        )
        assert any("tool_calls" in msg for msg in final_history)
        assert any(msg.get("role") == "tool" for msg in final_history)

    @pytest.mark.asyncio
    async def test_concurrent_session_access(self, grok_cache):
        """Test concurrent access to different sessions."""

        async def session_worker(session_id: str, message_count: int):
            history = []
            for i in range(message_count):
                history.append(
                    {"role": "user", "content": f"Message {i} for {session_id}"}
                )
                history.append(
                    {"role": "assistant", "content": f"Response {i} for {session_id}"}
                )
                await grok_cache.set_history(session_id, history)
            return await grok_cache.get_history(session_id)

        # Run multiple concurrent sessions
        tasks = [
            session_worker("concurrent-1", 3),
            session_worker("concurrent-2", 5),
            session_worker("concurrent-3", 2),
        ]

        results = await asyncio.gather(*tasks)

        # Verify each session maintained its own history
        assert len(results[0]) == 6  # 3 * 2 messages
        assert len(results[1]) == 10  # 5 * 2 messages
        assert len(results[2]) == 4  # 2 * 2 messages

        # Verify content is session-specific
        assert "concurrent-1" in results[0][0]["content"]
        assert "concurrent-2" in results[1][0]["content"]
        assert "concurrent-3" in results[2][0]["content"]
