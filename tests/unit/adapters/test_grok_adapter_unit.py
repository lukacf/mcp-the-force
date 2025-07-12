"""Unit tests for GrokAdapter class.

These tests verify the internal logic of GrokAdapter in isolation,
with all dependencies properly mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_second_brain.adapters.grok.adapter import GrokAdapter


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for unit testing."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    return client


@pytest.fixture
def grok_adapter_with_mock(mock_openai_client, mock_env):
    """Create GrokAdapter with mocked dependencies for unit testing."""
    with patch("mcp_second_brain.adapters.grok.adapter.AsyncOpenAI") as mock_openai:
        mock_openai.return_value = mock_openai_client

        adapter = GrokAdapter(model_name="grok-4")
        adapter.client = mock_openai_client
        return adapter


class TestGrokAdapterUnit:
    """Unit tests for GrokAdapter internal logic."""

    @pytest.mark.asyncio
    async def test_simple_conversation_without_tools(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Unit test: Simple conversation without tool calls."""
        # Mock response without tool calls
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Hello! How can I help you today?"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "Hello! How can I help you today?",
        }

        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Mock session cache to isolate the adapter
        with patch(
            "mcp_second_brain.adapters.grok.adapter.grok_session_cache",
            new_callable=AsyncMock,
        ) as mock_cache:
            mock_cache.get_history.return_value = []

            # FIX: Pass a session_id to trigger the history methods
            result = await grok_adapter_with_mock.generate(
                prompt="Hello", session_id="test-session-simple"
            )

            assert result == "Hello! How can I help you today?"

            # Verify adapter called session cache correctly
            mock_cache.get_history.assert_called_once_with("test-session-simple")
            mock_cache.set_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_tool_handling(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Unit test: Adapter handles unknown tool calls gracefully."""
        # FIX: Create two different mock responses for the two-step flow
        # 1. First response: The LLM asks to use an unknown tool
        mock_tool_call_response = MagicMock()
        mock_tool_call_response.choices = [MagicMock()]
        mock_tool_call_response.choices[0].message = MagicMock()
        mock_tool_call_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_unknown",
                function=MagicMock(name="unknown_tool_function", arguments="{}"),
            )
        ]
        mock_tool_call_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_unknown",
                    "type": "function",
                    "function": {"name": "unknown_tool_function", "arguments": "{}"},
                }
            ],
        }

        # 2. Second response: The LLM acknowledges the tool error and gives a final answer
        mock_final_response = MagicMock()
        mock_final_response.choices = [MagicMock()]
        mock_final_response.choices[0].message = MagicMock()
        mock_final_response.choices[
            0
        ].message.content = "I was unable to use the requested tool."
        mock_final_response.choices[0].message.tool_calls = None
        mock_final_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "I was unable to use the requested tool.",
        }

        # FIX: Use side_effect to return different responses on each call
        mock_openai_client.chat.completions.create = AsyncMock(
            side_effect=[mock_tool_call_response, mock_final_response]
        )

        # Mock session cache
        with patch(
            "mcp_second_brain.adapters.grok.adapter.grok_session_cache",
            new_callable=AsyncMock,
        ) as mock_cache:
            mock_cache.get_history.return_value = []

            result = await grok_adapter_with_mock.generate(prompt="Test unknown tool")

            # FIX: Assert against the final content from the second LLM call
            assert result == "I was unable to use the requested tool."

            # Verify the client was called twice (tool call, then final response)
            assert mock_openai_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_session_storage_called_correctly(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Unit test: Verify adapter calls session cache with correct parameters."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "Test response",
        }

        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Mock session cache to verify calls
        with patch(
            "mcp_second_brain.adapters.grok.adapter.grok_session_cache",
            new_callable=AsyncMock,
        ) as mock_cache:
            mock_cache.get_history.return_value = []

            await grok_adapter_with_mock.generate(
                prompt="Test message", session_id="test-session-123"
            )

            # Verify session cache was called with correct session ID
            mock_cache.get_history.assert_called_once_with("test-session-123")
            mock_cache.set_history.assert_called_once()

            # Check that history was stored with correct session ID
            call_args = mock_cache.set_history.call_args
            session_id_arg = call_args[0][0]
            assert session_id_arg == "test-session-123"
