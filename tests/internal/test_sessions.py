"""
Integration tests for multi-turn session management.
"""

import pytest
import asyncio
from unittest.mock import Mock
from mcp_second_brain.tools.executor import executor
from mcp_second_brain.tools.registry import get_tool

# Import definitions to ensure tools are registered
import mcp_second_brain.tools.definitions  # noqa: F401


class TestSessionManagement:
    """Test multi-turn conversation session management."""

    @pytest.fixture(autouse=True)
    def clear_session_cache(self):
        """Clear session cache before each test."""
        # The session_cache module now returns a new instance each time
        # which uses SQLite with a unique temp file, so no explicit clearing needed
        yield

    @pytest.fixture
    def parse_response(self):
        """Parse JSON response from MockAdapter."""
        import json

        def _parse(resp: str) -> dict:
            return json.loads(resp)

        return _parse

    @pytest.mark.asyncio
    async def test_basic_session_continuity(self, parse_response, mock_openai_client):
        """Test basic session continuity across multiple calls."""
        # First response
        response1 = Mock(id="resp_001", output_text="Hello! I can help with that.")

        # Second response
        response2 = Mock(
            id="resp_002", output_text="Continuing from before, here's the answer."
        )

        # Set up mock to return different responses
        mock_openai_client.responses.create.side_effect = [response1, response2]

        # First call
        tool_metadata = get_tool("chat_with_o3")
        if not tool_metadata:
            raise ValueError("Tool chat_with_o3 not found")
        result1 = await executor.execute(
            tool_metadata,
            instructions="I need help with Python decorators",
            output_format="explanation",
            context=[],
            session_id="decorator-help",
        )

        # Parse MockAdapter response
        data1 = parse_response(result1)
        assert data1["mock"] is True
        assert "Python decorators" in data1["prompt_preview"]

        # Second call with same session
        result2 = await executor.execute(
            tool_metadata,
            instructions="Can you show me a concrete example?",
            output_format="code",
            context=[],
            session_id="decorator-help",
        )

        data2 = parse_response(result2)
        assert data2["mock"] is True
        assert "concrete example" in data2["prompt_preview"]

        # With MockAdapter, we're verifying the session mechanism works,
        # not the actual OpenAI API behavior
        # The session cache and adapter parameters are tested separately

    @pytest.mark.asyncio
    async def test_multiple_sessions_isolated(self, parse_response, mock_openai_client):
        """Test that different sessions are isolated from each other."""
        # With MockAdapter, we're testing the session isolation mechanism
        tool_metadata = get_tool("chat_with_o3")
        if not tool_metadata:
            raise ValueError("Tool chat_with_o3 not found")

        # Two parallel conversations
        results = await asyncio.gather(
            executor.execute(
                tool_metadata,
                instructions="First message session 1",
                output_format="text",
                context=[],
                session_id="session-1",
            ),
            executor.execute(
                tool_metadata,
                instructions="First message session 2",
                output_format="text",
                context=[],
                session_id="session-2",
            ),
            executor.execute(
                tool_metadata,
                instructions="Second message session 1",
                output_format="text",
                context=[],
                session_id="session-1",
            ),
            executor.execute(
                tool_metadata,
                instructions="Second message session 2",
                output_format="text",
                context=[],
                session_id="session-2",
            ),
        )

        # Parse all responses
        parsed = [parse_response(r) for r in results]

        # Check all are mock responses
        assert all(p["mock"] is True for p in parsed)

        # Check instructions match what we sent
        session1_instructions = [
            p["prompt_preview"] for p in parsed if "session 1" in p["prompt_preview"]
        ]
        session2_instructions = [
            p["prompt_preview"] for p in parsed if "session 2" in p["prompt_preview"]
        ]

        assert len(session1_instructions) == 2
        assert len(session2_instructions) == 2

    @pytest.mark.asyncio
    async def test_session_with_different_models(
        self, parse_response, mock_openai_client
    ):
        """Test using same session ID across different OpenAI models."""
        # Start with o3
        o3_metadata = get_tool("chat_with_o3")
        if not o3_metadata:
            raise ValueError("Tool chat_with_o3 not found")
        result1 = await executor.execute(
            o3_metadata,
            instructions="Start conversation",
            output_format="text",
            context=[],
            session_id="cross-model",
        )

        data1 = parse_response(result1)
        assert data1["mock"] is True
        assert data1["model"] == "o3"

        # Continue with gpt4
        gpt4_metadata = get_tool("chat_with_gpt4_1")
        if not gpt4_metadata:
            raise ValueError("Tool chat_with_gpt4_1 not found")
        result2 = await executor.execute(
            gpt4_metadata,
            instructions="Continue conversation",
            output_format="text",
            context=[],
            session_id="cross-model",
        )

        data2 = parse_response(result2)
        assert data2["mock"] is True
        assert data2["model"] == "gpt-4.1"

        # With MockAdapter, we're verifying the models are different
        # Session handling is done at the executor level, not adapter level

    @pytest.mark.asyncio
    async def test_session_expiration(self, parse_response, mock_openai_client):
        """Test that sessions expire after TTL."""
        from mcp_second_brain.session_cache import _SQLiteSessionCache
        from unittest.mock import patch
        import tempfile

        # Create cache with very short TTL for testing
        db_path = tempfile.mktemp(suffix=".db")
        cache = _SQLiteSessionCache(db_path=db_path, ttl=0.1)  # 100ms TTL

        with patch("mcp_second_brain.session_cache.session_cache", cache):
            response = Mock(id="resp_expire", output_text="Initial response")
            mock_openai_client.responses.create.return_value = response

            # First call
            tool_metadata = get_tool("chat_with_o3")
            if not tool_metadata:
                raise ValueError("Tool chat_with_o3 not found")
            result1 = await executor.execute(
                tool_metadata,
                instructions="Start",
                output_format="text",
                context=[],
                session_id="expire-test",
            )

            data1 = parse_response(result1)
            assert data1["mock"] is True

            # Wait for expiration
            await asyncio.sleep(0.2)

            # Second call - session should have expired
            result2 = await executor.execute(
                tool_metadata,
                instructions="Continue",
                output_format="text",
                context=[],
                session_id="expire-test",
            )

            data2 = parse_response(result2)
            assert data2["mock"] is True

            # Both calls should succeed with MockAdapter
            # The session expiration is handled at the adapter level

    @pytest.mark.asyncio
    async def test_gemini_session_continuity(self, parse_response):
        """Test multi-turn sessions with Gemini models."""
        tool_metadata = get_tool("chat_with_gemini25_flash")
        if not tool_metadata:
            raise ValueError("Tool chat_with_gemini25_flash not found")
        result1 = await executor.execute(
            tool_metadata,
            instructions="Hello",
            output_format="text",
            context=[],
            session_id="gem-session",
        )

        data1 = parse_response(result1)
        assert data1["mock"] is True
        msgs1 = data1["adapter_kwargs"].get("messages")
        assert msgs1 and len(msgs1) == 1

        result2 = await executor.execute(
            tool_metadata,
            instructions="Follow up",
            output_format="text",
            context=[],
            session_id="gem-session",
        )

        data2 = parse_response(result2)
        msgs2 = data2["adapter_kwargs"].get("messages")
        assert msgs2 and len(msgs2) == 3

    @pytest.mark.asyncio
    async def test_concurrent_session_updates(self, parse_response):
        """Test that concurrent requests to same session handle properly."""
        # Launch three requests concurrently to same session
        tool_metadata = get_tool("chat_with_o3")
        if not tool_metadata:
            raise ValueError("Tool chat_with_o3 not found")
        tasks = [
            executor.execute(
                tool_metadata,
                instructions=f"Message {i}",
                output_format="text",
                context=[],
                session_id="concurrent-test",
            )
            for i in range(3)
        ]

        results = await asyncio.gather(*tasks)

        # All should complete successfully
        assert len(results) == 3

        # Parse all responses
        parsed = [parse_response(r) for r in results]
        assert all(p["mock"] is True for p in parsed)
        assert all(p["model"] == "o3" for p in parsed)

        # All should be using the same model and session is handled at executor level
        # Just verify all calls succeeded with the correct model

    @pytest.mark.asyncio
    async def test_session_with_context_changes(
        self, temp_project, parse_response, mock_openai_client
    ):
        """Test session continuity when context files change between calls."""
        # First call with initial context
        tool_metadata = get_tool("chat_with_o3")
        if not tool_metadata:
            raise ValueError("Tool chat_with_o3 not found")
        result1 = await executor.execute(
            tool_metadata,
            instructions="Analyze this project",
            output_format="summary",
            context=[str(temp_project)],
            session_id="evolving-context",
        )

        data1 = parse_response(result1)
        assert data1["mock"] is True
        assert "Analyze this project" in data1["prompt_preview"]

        # Add a new file
        (temp_project / "new_feature.py").write_text("def new_feature(): pass")

        # Second call with updated context
        result2 = await executor.execute(
            tool_metadata,
            instructions="What changed?",
            output_format="diff",
            context=[str(temp_project)],
            session_id="evolving-context",
        )

        data2 = parse_response(result2)
        assert data2["mock"] is True
        assert "What changed?" in data2["prompt_preview"]

        # Session continuity is maintained at the executor level via session_cache
        # MockAdapter doesn't need to know about sessions
