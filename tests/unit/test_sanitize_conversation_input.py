"""Tests for _sanitize_conversation_input function.

These tests ensure the sanitization function correctly handles edge cases
that cause provider-specific errors (especially Anthropic/Claude).
"""

from mcp_the_force.adapters.litellm_base import _sanitize_conversation_input


class TestSanitizeMessageContent:
    """Tests for message content sanitization."""

    def test_sanitize_message_with_none_content(self):
        """Ensure messages with content=None get placeholder content.

        Regression test: Claude rejects messages with content=None with error:
        "Invalid content type: <class 'NoneType'>"
        """
        conversation = [{"type": "message", "role": "user", "content": None}]

        _sanitize_conversation_input(conversation)

        assert conversation[0]["content"] == [{"type": "text", "text": "(empty)"}]

    def test_sanitize_message_with_empty_text_content(self):
        """Ensure messages with empty text get placeholder text.

        Regression test: Claude rejects with error:
        "text content blocks must be non-empty"
        """
        conversation = [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": ""}],
            }
        ]

        _sanitize_conversation_input(conversation)

        assert conversation[0]["content"][0]["text"] == "(empty)"

    def test_sanitize_message_with_none_text_in_content(self):
        """Ensure None text values are replaced with placeholder."""
        conversation = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": None}],
            }
        ]

        _sanitize_conversation_input(conversation)

        assert conversation[0]["content"][0]["text"] == "(empty)"

    def test_preserves_valid_message_content(self):
        """Ensure valid content is not modified."""
        conversation = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            }
        ]

        _sanitize_conversation_input(conversation)

        assert conversation[0]["content"][0]["text"] == "Hello"


class TestSanitizeFunctionCallContent:
    """Tests for function_call item sanitization."""

    def test_function_call_removed_from_input(self):
        """function_call items should be removed from the conversation input.

        Regression test: litellm doesn't know how to handle function_call items
        in the input - it expects them to be in TOOL_CALLS_CACHE. So we register
        them in the cache and remove them from the input.
        """
        conversation = [
            {
                "type": "function_call",
                "call_id": "call_123",
                "name": "test_func",
                "arguments": "{}",
                "content": None,
            }
        ]

        _sanitize_conversation_input(conversation)

        # function_call items are removed from input
        assert len(conversation) == 0

    def test_function_call_with_none_arguments_registered_correctly(self):
        """function_call items with None arguments should be handled properly."""
        conversation = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            },
            {
                "type": "function_call",
                "call_id": "call_123",
                "name": "test_func",
                "arguments": None,
            },
        ]

        _sanitize_conversation_input(conversation)

        # function_call removed, only message remains
        assert len(conversation) == 1
        assert conversation[0]["type"] == "message"


class TestSanitizeFunctionCallOutputContent:
    """Tests for function_call_output item sanitization."""

    def test_removes_content_from_function_call_output(self):
        """Ensure spurious content field is removed from function_call_output items.

        Regression test: Claude doesn't expect content on function_call_output items.
        """
        conversation = [
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "result",
                "content": None,
            }
        ]

        _sanitize_conversation_input(conversation)

        assert "content" not in conversation[0]
        assert conversation[0]["output"] == "result"

    def test_adds_empty_output_if_none(self):
        """Ensure function_call_output gets empty output if None."""
        conversation = [
            {"type": "function_call_output", "call_id": "call_123", "output": None}
        ]

        _sanitize_conversation_input(conversation)

        assert conversation[0]["output"] == ""


class TestSanitizeMalformedItems:
    """Tests for malformed conversation items."""

    def test_adds_type_to_item_with_role_but_no_type(self):
        """Items with role but missing type should get type='message' added.

        Regression test: Session history may have malformed items.
        """
        conversation = [
            {"role": "user", "content": [{"type": "text", "text": "Hello"}]}
        ]

        _sanitize_conversation_input(conversation)

        assert conversation[0]["type"] == "message"
        assert conversation[0]["content"][0]["text"] == "Hello"

    def test_adds_type_and_content_to_item_with_only_role(self):
        """Items with role but missing type and content should be fixed."""
        conversation = [{"role": "assistant"}]

        _sanitize_conversation_input(conversation)

        assert conversation[0]["type"] == "message"
        assert conversation[0]["content"] == [{"type": "text", "text": "(empty)"}]

    def test_handles_unknown_type_with_content_none(self):
        """Unknown item types with content=None should have content removed.

        Regression test: litellm calls .get("content") on ALL items.
        """
        conversation = [{"type": "some_unknown_type", "content": None, "data": "test"}]

        _sanitize_conversation_input(conversation)

        assert "content" not in conversation[0]
        assert conversation[0]["data"] == "test"


class TestSanitizeCompleteConversation:
    """Integration tests for full conversation sanitization."""

    def test_sanitize_realistic_conversation_with_tool_calls(self):
        """Test sanitizing a realistic conversation with tool calls and responses.

        Note: function_call items are REMOVED from input (registered in litellm's cache instead).
        """
        conversation = [
            {
                "type": "message",
                "role": "system",
                "content": [{"type": "text", "text": "You are a helpful assistant."}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": None,
            },  # Bad: None content
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "get_time",
                "arguments": "{}",
                "content": None,
            },
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": "12:00",
                "content": None,
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": ""}],
            },  # Bad: empty text
        ]

        _sanitize_conversation_input(conversation)

        # After sanitization: 5 items (function_call removed)
        assert len(conversation) == 5

        # System message unchanged
        assert conversation[0]["content"][0]["text"] == "You are a helpful assistant."

        # User message unchanged
        assert conversation[1]["content"][0]["text"] == "Hello"

        # Assistant message with None content gets placeholder
        assert conversation[2]["content"] == [{"type": "text", "text": "(empty)"}]

        # function_call was REMOVED (index 3 is now function_call_output)
        assert conversation[3]["type"] == "function_call_output"
        assert "content" not in conversation[3]

        # Assistant message with empty text gets placeholder (now at index 4)
        assert conversation[4]["content"][0]["text"] == "(empty)"

    def test_idempotent_sanitization(self):
        """Sanitizing twice should produce the same result."""
        conversation = [
            {"type": "message", "role": "user", "content": None},
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "test",
                "arguments": None,
            },
        ]

        _sanitize_conversation_input(conversation)
        first_pass = [dict(item) for item in conversation]

        _sanitize_conversation_input(conversation)
        second_pass = [dict(item) for item in conversation]

        # After first pass: function_call removed, only message remains
        # After second pass: same (no more function_calls to remove)
        assert first_pass == second_pass
        assert len(first_pass) == 1  # Only the message remains
