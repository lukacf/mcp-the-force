"""Unit tests for message format integrity through adapter layers.

This test suite ensures that message formats are preserved correctly
as they flow through the adapter system, preventing issues like:
- Double conversion/wrapping of messages
- Format corruption when loading from cache
- Loss of message structure
- Incorrect assumptions about message format
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from typing import Dict, Any, List
import json

from mcp_the_force.adapters.litellm_base import LiteLLMBaseAdapter
from mcp_the_force.adapters.protocol import CallContext
from mcp_the_force.adapters.capabilities import AdapterCapabilities


class MockTestAdapter(LiteLLMBaseAdapter):
    """Concrete test adapter for testing."""

    def __init__(self):
        self.model_name = "test-model"
        self.display_name = "Test Adapter"
        self.capabilities = AdapterCapabilities(
            supports_structured_output=True,
            supports_vision=False,
        )
        super().__init__()

    def _validate_environment(self):
        pass

    def _get_model_prefix(self) -> str:
        return "test"

    def _build_request_params(
        self,
        conversation_input: List[Dict[str, Any]],
        params: Any,
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return {
            "model": f"{self._get_model_prefix()}/{self.model_name}",
            "input": conversation_input,
        }


class TestParams:
    """Test parameters."""

    structured_output_schema: str = None
    disable_history_search: bool = False


def create_responses_api_message(role: str, content: str) -> Dict[str, Any]:
    """Create a properly formatted Responses API message."""
    return {
        "type": "message",
        "role": role,
        "content": [{"type": "text", "text": content}],
    }


def create_tool_result(call_id: str, output: str) -> Dict[str, Any]:
    """Create a properly formatted tool result."""
    return {"type": "function_call_output", "call_id": call_id, "output": output}


def assert_message_format_valid(msg: Dict[str, Any]):
    """Assert that a message is in valid Responses API format."""
    assert isinstance(msg, dict), "Message must be a dict"
    assert "type" in msg, "Message must have 'type' field"

    if msg["type"] == "message":
        assert "role" in msg, "Message must have 'role' field"
        assert msg["role"] in [
            "system",
            "user",
            "assistant",
        ], f"Invalid role: {msg['role']}"
        assert "content" in msg, "Message must have 'content' field"
        assert isinstance(msg["content"], list), "Content must be a list"

        for content_item in msg["content"]:
            assert isinstance(content_item, dict), "Content item must be a dict"
            assert "type" in content_item, "Content item must have 'type'"
            if content_item["type"] == "text":
                assert "text" in content_item, "Text content must have 'text' field"
                assert isinstance(content_item["text"], str), "Text must be a string"

    elif msg["type"] == "function_call_output":
        assert "call_id" in msg, "Tool result must have 'call_id'"
        assert "output" in msg, "Tool result must have 'output'"
        assert isinstance(msg["output"], str), "Output must be a string"


@pytest.mark.asyncio
async def test_format_preservation_through_full_cycle():
    """Test that message format is preserved through save/load/send cycle."""
    adapter = MockTestAdapter()

    # Create a complex conversation with various message types
    original_messages = [
        create_responses_api_message("user", "First question"),
        create_responses_api_message("assistant", "First response"),
        create_tool_result("call_123", "Tool output"),
        create_responses_api_message(
            "user", "Second question with 'quotes' and {json}"
        ),
        create_responses_api_message("assistant", '{"result": "json response"}'),
    ]

    with patch("mcp_the_force.adapters.litellm_base.UnifiedSessionCache") as mock_cache:
        with patch(
            "mcp_the_force.adapters.litellm_base.aresponses", new_callable=AsyncMock
        ) as mock_aresponses:
            # Configure mocks
            mock_cache.get_history = AsyncMock(return_value=original_messages.copy())
            mock_cache.set_history = AsyncMock()

            mock_response = Mock()
            mock_response.output = [
                Mock(type="message", content=[Mock(text="New response")])
            ]
            mock_aresponses.return_value = mock_response

            # Execute
            ctx = CallContext(
                session_id="test-session", project="test-project", tool="test-tool"
            )
            params = TestParams()
            tool_dispatcher = Mock()
            tool_dispatcher.get_tool_declarations.return_value = []

            await adapter.generate(
                prompt="Third question",
                params=params,
                ctx=ctx,
                tool_dispatcher=tool_dispatcher,
            )

            # Verify messages sent to LiteLLM are exactly as expected
            assert mock_aresponses.called
            sent_messages = mock_aresponses.call_args[1]["input"]

            # Should have original 5 + 1 new message
            assert len(sent_messages) == 6

            # Original messages should be EXACTLY preserved
            for i, original_msg in enumerate(original_messages):
                assert sent_messages[i] == original_msg, (
                    f"Message {i} was corrupted. "
                    f"Original: {json.dumps(original_msg, indent=2)}\n"
                    f"Sent: {json.dumps(sent_messages[i], indent=2)}"
                )

            # New message should be properly formatted
            new_msg = sent_messages[5]
            assert_message_format_valid(new_msg)
            assert new_msg["role"] == "user"
            assert "Third question" in new_msg["content"][0]["text"]

            # Verify saved conversation preserves format
            assert mock_cache.set_history.called
            saved_messages = mock_cache.set_history.call_args[0][
                2
            ]  # 3rd argument after project, session_id (no tool)

            # Should have all messages plus assistant response
            assert len(saved_messages) == 7

            # All messages should be in valid format
            for msg in saved_messages:
                assert_message_format_valid(msg)


@pytest.mark.asyncio
async def test_no_format_assumptions():
    """Test that adapter doesn't make assumptions about message format."""
    adapter = MockTestAdapter()

    # Test various edge cases that might break format assumptions
    edge_cases = [
        # Message with nested JSON in content
        create_responses_api_message(
            "user", json.dumps({"nested": {"data": [1, 2, 3]}})
        ),
        # Message with special characters
        create_responses_api_message(
            "assistant", "Text with \n newlines \t tabs and 'quotes'"
        ),
        # Empty content
        create_responses_api_message("user", ""),
        # Very long content
        create_responses_api_message("assistant", "x" * 10000),
    ]

    for test_msg in edge_cases:
        with patch(
            "mcp_the_force.adapters.litellm_base.UnifiedSessionCache"
        ) as mock_cache:
            with patch(
                "mcp_the_force.adapters.litellm_base.aresponses", new_callable=AsyncMock
            ) as mock_aresponses:
                mock_cache.get_history = AsyncMock(return_value=[test_msg])
                mock_cache.set_history = AsyncMock()

                mock_response = Mock()
                mock_response.output = [
                    Mock(type="message", content=[Mock(text="Response")])
                ]
                mock_aresponses.return_value = mock_response

                ctx = CallContext(
                    session_id="edge-test", project="test-project", tool="test-tool"
                )
                params = TestParams()

                await adapter.generate(
                    prompt="Test",
                    params=params,
                    ctx=ctx,
                    tool_dispatcher=Mock(get_tool_declarations=Mock(return_value=[])),
                )

                # Verify the message was passed through unchanged
                sent_messages = mock_aresponses.call_args[1]["input"]
                assert sent_messages[0] == test_msg


@pytest.mark.asyncio
async def test_round_trip_integrity():
    """Test that messages can make a full round trip without corruption."""
    adapter = MockTestAdapter()

    # Simulate multiple round trips
    conversation = []

    for round_num in range(3):
        with patch(
            "mcp_the_force.adapters.litellm_base.UnifiedSessionCache"
        ) as mock_cache:
            with patch(
                "mcp_the_force.adapters.litellm_base.aresponses", new_callable=AsyncMock
            ) as mock_aresponses:
                # Load existing conversation
                mock_cache.get_history = AsyncMock(return_value=conversation.copy())
                saved_conversation = None

                def capture_save(project, session_id, messages):
                    nonlocal saved_conversation
                    saved_conversation = messages.copy()
                    return AsyncMock()()

                mock_cache.set_history = AsyncMock(side_effect=capture_save)

                # Mock response
                mock_response = Mock()
                mock_response.output = [
                    Mock(type="message", content=[Mock(text=f"Response {round_num}")])
                ]
                mock_aresponses.return_value = mock_response

                ctx = CallContext(
                    session_id="round-trip", project="test-project", tool="test-tool"
                )
                params = TestParams()

                await adapter.generate(
                    prompt=f"Question {round_num}",
                    params=params,
                    ctx=ctx,
                    tool_dispatcher=Mock(get_tool_declarations=Mock(return_value=[])),
                )

                # Update conversation for next round
                conversation = saved_conversation

                # Verify all messages are still valid
                for msg in conversation:
                    assert_message_format_valid(msg)

    # After 3 rounds, should have 6 messages (3 user + 3 assistant)
    assert len(conversation) == 6

    # Verify conversation structure is coherent
    for i in range(3):
        user_msg = conversation[i * 2]
        assistant_msg = conversation[i * 2 + 1]

        assert user_msg["role"] == "user"
        assert f"Question {i}" in user_msg["content"][0]["text"]

        assert assistant_msg["role"] == "assistant"
        assert f"Response {i}" in assistant_msg["content"][0]["text"]


@pytest.mark.asyncio
async def test_tool_call_format_preservation():
    """Test that tool calls maintain correct format through the system."""
    adapter = MockTestAdapter()

    with patch("mcp_the_force.adapters.litellm_base.UnifiedSessionCache") as mock_cache:
        with patch(
            "mcp_the_force.adapters.litellm_base.aresponses", new_callable=AsyncMock
        ) as mock_aresponses:
            mock_cache.get_history = AsyncMock(return_value=[])
            mock_cache.set_history = AsyncMock()

            # First response includes tool calls
            first_response = Mock()
            first_response.output = [
                Mock(type="message", content=[Mock(text="Let me search for that")]),
                Mock(
                    type="function_call",
                    name="search_files",
                    call_id="call_abc",
                    arguments={"query": "test"},
                ),
            ]

            # Second response after tool execution
            second_response = Mock()
            second_response.output = [
                Mock(
                    type="message",
                    content=[Mock(text="Based on the search results...")],
                )
            ]

            mock_aresponses.side_effect = [first_response, second_response]

            # Mock tool dispatcher
            tool_dispatcher = Mock()
            tool_dispatcher.get_tool_declarations.return_value = []
            tool_dispatcher.execute = AsyncMock(return_value="Found 3 files")

            ctx = CallContext(
                session_id="tool-test", project="test-project", tool="test-tool"
            )
            params = TestParams()

            await adapter.generate(
                prompt="Search for test files",
                params=params,
                ctx=ctx,
                tool_dispatcher=tool_dispatcher,
            )

            # Verify tool was called
            tool_dispatcher.execute.assert_called_once()

            # Verify second API call includes tool result in correct format
            second_call_messages = mock_aresponses.call_args_list[1][1]["input"]

            # Should have: user message, assistant message, tool result, continued conversation
            tool_result_msg = None
            for msg in second_call_messages:
                if msg.get("type") == "function_call_output":
                    tool_result_msg = msg
                    break

            assert tool_result_msg is not None
            assert tool_result_msg["call_id"] == "call_abc"
            assert tool_result_msg["output"] == "Found 3 files"


@pytest.mark.asyncio
async def test_content_type_variations():
    """Test that different content types are handled correctly."""
    adapter = MockTestAdapter()

    # Test messages with different content structures
    test_cases = [
        # Standard text content
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "text", "text": "Standard message"}],
        },
        # Multiple content items (future: could include images)
        {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "text", "text": "Part 1"},
                {"type": "text", "text": "Part 2"},
            ],
        },
        # System message
        {
            "type": "message",
            "role": "system",
            "content": [{"type": "text", "text": "System prompt"}],
        },
    ]

    for test_msg in test_cases:
        with patch(
            "mcp_the_force.adapters.litellm_base.UnifiedSessionCache"
        ) as mock_cache:
            with patch(
                "mcp_the_force.adapters.litellm_base.aresponses", new_callable=AsyncMock
            ) as mock_aresponses:
                mock_cache.get_history = AsyncMock(return_value=[test_msg])
                mock_cache.set_history = AsyncMock()

                mock_response = Mock()
                mock_response.output = [Mock(type="message", content=[Mock(text="OK")])]
                mock_aresponses.return_value = mock_response

                ctx = CallContext(
                    session_id="content-test", project="test-project", tool="test-tool"
                )

                await adapter.generate(
                    prompt="Test",
                    params=TestParams(),
                    ctx=ctx,
                    tool_dispatcher=Mock(get_tool_declarations=Mock(return_value=[])),
                )

                # Message should pass through unchanged
                sent_messages = mock_aresponses.call_args[1]["input"]
                assert sent_messages[0] == test_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
