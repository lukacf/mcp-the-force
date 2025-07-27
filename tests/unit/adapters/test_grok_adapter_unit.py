"""Unit tests for GrokAdapter class.

These tests verify the internal logic of GrokAdapter in isolation,
with all dependencies properly mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from mcp_the_force.adapters.xai.adapter import GrokAdapter
from mcp_the_force.adapters.protocol import CallContext


@pytest.fixture
def mock_litellm_response():
    """Mock LiteLLM Responses API response object."""
    response = MagicMock()

    # Create a message item with content
    message_item = MagicMock()
    message_item.type = "message"
    message_item.content = "Hello! How can I help you today?"

    # Set up the output attribute (Responses API format)
    response.output = [message_item]

    return response


@pytest.fixture
def grok_adapter_with_mock(mock_env):
    """Create GrokAdapter with mocked dependencies for unit testing."""
    adapter = GrokAdapter(model="grok-4")
    return adapter


class TestGrokAdapterUnit:
    """Unit tests for GrokAdapter internal logic."""

    @pytest.mark.asyncio
    async def test_simple_conversation_without_tools(
        self, grok_adapter_with_mock, mock_litellm_response
    ):
        """Unit test: Simple conversation without tool calls."""
        # Mock litellm.aresponses
        with patch("litellm.aresponses") as mock_aresponses:
            mock_aresponses.return_value = mock_litellm_response

            # Mock unified session cache to isolate the adapter
            with patch(
                "mcp_the_force.adapters.xai.adapter.unified_session_cache",
                new_callable=AsyncMock,
            ) as mock_cache:
                mock_cache.get_history.return_value = []

                # Create params and context for protocol-based adapter
                params = SimpleNamespace(
                    instructions="Hello",
                    output_format="",
                    context=[],
                    session_id="test-session-simple",
                    temperature=0.7,
                    search_mode="auto",
                    search_parameters=None,
                    return_citations=True,
                    reasoning_effort=None,
                    disable_memory_search=False,
                    structured_output_schema=None,
                )

                ctx = CallContext(session_id="test-session-simple")

                # Mock tool dispatcher with empty tools
                mock_dispatcher = MagicMock()
                mock_dispatcher.get_tool_declarations.return_value = []

                result = await grok_adapter_with_mock.generate(
                    prompt="Hello",
                    params=params,
                    ctx=ctx,
                    tool_dispatcher=mock_dispatcher,
                )

                assert result["content"] == "Hello! How can I help you today?"

                # Verify adapter called session cache correctly
                mock_cache.get_history.assert_called_once_with("test-session-simple")
                mock_cache.set_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_tool_handling(self, grok_adapter_with_mock):
        """Unit test: Adapter handles unknown tool calls gracefully."""
        # Create two different mock responses for the two-step flow
        # 1. First response: The LLM asks to use an unknown tool
        mock_tool_call_response = MagicMock()

        # Create a function call item
        function_call_item = MagicMock()
        function_call_item.type = "function_call"
        function_call_item.call_id = "call_unknown"
        function_call_item.name = "unknown_tool_function"
        function_call_item.arguments = "{}"

        # Set up the output attribute (Responses API format)
        mock_tool_call_response.output = [function_call_item]

        # 2. Second response: The LLM acknowledges the tool error and gives a final answer
        mock_final_response = MagicMock()

        # Create a message item with content
        message_item = MagicMock()
        message_item.type = "message"
        message_item.content = "I was unable to use the requested tool."

        # Set up the output attribute (Responses API format)
        mock_final_response.output = [message_item]

        # Mock litellm.aresponses with side_effect
        with patch("litellm.aresponses") as mock_aresponses:
            mock_aresponses.side_effect = [mock_tool_call_response, mock_final_response]

            # Mock session cache
            with patch(
                "mcp_the_force.adapters.xai.adapter.unified_session_cache",
                new_callable=AsyncMock,
            ) as mock_cache:
                mock_cache.get_history.return_value = []

                # Create params and context
                params = SimpleNamespace(
                    instructions="Test unknown tool",
                    output_format="",
                    context=[],
                    session_id="",
                    temperature=0.7,
                    search_mode="auto",
                    search_parameters=None,
                    return_citations=True,
                    reasoning_effort=None,
                    disable_memory_search=False,
                    structured_output_schema=None,
                )

                ctx = CallContext(session_id="")

                # Mock tool dispatcher that doesn't have the unknown tool
                mock_dispatcher = MagicMock()
                mock_dispatcher.execute = AsyncMock(
                    side_effect=Exception("Unknown tool: unknown_tool_function")
                )

                result = await grok_adapter_with_mock.generate(
                    prompt="Test unknown tool",
                    params=params,
                    ctx=ctx,
                    tool_dispatcher=mock_dispatcher,
                )

                # Assert against the final content from the second LLM call
                assert result["content"] == "I was unable to use the requested tool."

                # Verify aresponses was called twice (tool call, then final response)
                assert mock_aresponses.call_count == 2

    @pytest.mark.asyncio
    async def test_session_storage_called_correctly(self, grok_adapter_with_mock):
        """Unit test: Verify adapter calls session cache with correct parameters."""
        mock_response = MagicMock()

        # Create a message item with content
        message_item = MagicMock()
        message_item.type = "message"
        message_item.content = "Test response"

        # Set up the output attribute (Responses API format)
        mock_response.output = [message_item]

        # Mock litellm.aresponses
        with patch("litellm.aresponses") as mock_aresponses:
            mock_aresponses.return_value = mock_response

            # Mock session cache to verify calls
            with patch(
                "mcp_the_force.adapters.xai.adapter.unified_session_cache",
                new_callable=AsyncMock,
            ) as mock_cache:
                mock_cache.get_history.return_value = []

                # Create params and context
                params = SimpleNamespace(
                    instructions="Test message",
                    output_format="",
                    context=[],
                    session_id="test-session-123",
                    temperature=0.7,
                    search_mode="auto",
                    search_parameters=None,
                    return_citations=True,
                    reasoning_effort=None,
                    disable_memory_search=False,
                    structured_output_schema=None,
                )

                ctx = CallContext(session_id="test-session-123")

                # Mock tool dispatcher with empty tools
                mock_dispatcher = MagicMock()
                mock_dispatcher.get_tool_declarations.return_value = []

                await grok_adapter_with_mock.generate(
                    prompt="Test message",
                    params=params,
                    ctx=ctx,
                    tool_dispatcher=mock_dispatcher,
                )

                # Verify session cache was called with correct session ID
                mock_cache.get_history.assert_called_once_with("test-session-123")
                mock_cache.set_history.assert_called_once()

                # Check that history was stored with correct session ID
                call_args = mock_cache.set_history.call_args
                session_id_arg = call_args[0][0]
                assert session_id_arg == "test-session-123"
