"""Tests for google-genai format converters."""

from google.genai import types

from mcp_the_force.adapters.google.converters import (
    responses_to_contents,
    content_to_responses,
    tools_to_gemini,
)


class TestResponsesToContents:
    """Test conversion from Responses API format to google-genai Content."""

    def test_empty_history(self):
        """Empty history returns empty list."""
        result = responses_to_contents([])
        assert result == []

    def test_simple_user_message(self):
        """Convert a simple user message."""
        history = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            }
        ]
        result = responses_to_contents(history)

        assert len(result) == 1
        assert result[0].role == "user"
        assert len(result[0].parts) == 1
        assert result[0].parts[0].text == "Hello"

    def test_simple_assistant_message(self):
        """Convert a simple assistant message."""
        history = [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there!"}],
            }
        ]
        result = responses_to_contents(history)

        assert len(result) == 1
        assert result[0].role == "model"
        assert result[0].parts[0].text == "Hi there!"

    def test_multi_turn_conversation(self):
        """Convert a multi-turn conversation."""
        history = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi!"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "How are you?"}],
            },
        ]
        result = responses_to_contents(history)

        assert len(result) == 3
        assert result[0].role == "user"
        assert result[1].role == "model"
        assert result[2].role == "user"

    def test_function_call_basic(self):
        """Convert a function call without thought_signature."""
        history = [
            {
                "type": "function_call",
                "name": "get_weather",
                "call_id": "call_123",
                "arguments": '{"location": "NYC"}',
            }
        ]
        result = responses_to_contents(history)

        assert len(result) == 1
        assert result[0].role == "model"
        assert len(result[0].parts) == 1

        fc = result[0].parts[0].function_call
        assert fc.name == "get_weather"
        assert fc.args == {"location": "NYC"}
        assert fc.id == "call_123"

    def test_function_call_with_thought_signature(self):
        """Convert a function call preserving thought_signature."""
        history = [
            {
                "type": "function_call",
                "name": "search",
                "call_id": "call_456",
                "arguments": '{"query": "test"}',
                "thought_signature": "signature_bytes_here",
            }
        ]
        result = responses_to_contents(history)

        assert len(result) == 1
        part = result[0].parts[0]
        assert part.function_call.name == "search"
        assert part.thought_signature == b"signature_bytes_here"

    def test_function_call_output(self):
        """Convert function call output."""
        history = [
            {
                "type": "function_call",
                "name": "get_weather",
                "call_id": "call_123",
                "arguments": "{}",
            },
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "Sunny, 72F",
            },
        ]
        result = responses_to_contents(history)

        assert len(result) == 2
        # First is the function call (model turn)
        assert result[0].role == "model"
        # Second is the function response (user turn)
        assert result[1].role == "user"

        fr = result[1].parts[0].function_response
        assert fr.id == "call_123"
        assert fr.name == "get_weather"
        assert fr.response == {"result": "Sunny, 72F"}

    def test_consecutive_function_calls_grouped(self):
        """Multiple consecutive function calls should be in one Content."""
        history = [
            {
                "type": "function_call",
                "name": "func1",
                "call_id": "call_1",
                "arguments": "{}",
            },
            {
                "type": "function_call",
                "name": "func2",
                "call_id": "call_2",
                "arguments": "{}",
            },
        ]
        result = responses_to_contents(history)

        # Should be one Content with two parts
        assert len(result) == 1
        assert len(result[0].parts) == 2
        assert result[0].parts[0].function_call.name == "func1"
        assert result[0].parts[1].function_call.name == "func2"

    def test_full_tool_interaction(self):
        """Test a complete tool interaction flow."""
        history = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "What's the weather?"}],
            },
            {
                "type": "function_call",
                "name": "get_weather",
                "call_id": "call_123",
                "arguments": '{"location": "NYC"}',
                "thought_signature": "sig123",
            },
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "Sunny, 72F",
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "It's sunny and 72F in NYC."}],
            },
        ]
        result = responses_to_contents(history)

        assert len(result) == 4
        assert result[0].role == "user"  # User question
        assert result[1].role == "model"  # Function call
        assert result[1].parts[0].thought_signature == b"sig123"
        assert result[2].role == "user"  # Function response
        assert result[3].role == "model"  # Assistant answer


class TestContentToResponses:
    """Test conversion from google-genai Content to Responses API format."""

    def test_text_content(self):
        """Convert Content with text to Responses format."""
        content = types.Content(
            role="model",
            parts=[types.Part(text="Hello world")],
        )
        result = content_to_responses(content)

        assert len(result) == 1
        assert result[0]["type"] == "message"
        assert result[0]["role"] == "assistant"
        assert result[0]["content"][0]["text"] == "Hello world"

    def test_function_call_content(self):
        """Convert Content with function call to Responses format."""
        content = types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="test_func",
                        args={"arg1": "value1"},
                        id="call_789",
                    ),
                    thought_signature=b"test_signature",
                )
            ],
        )
        result = content_to_responses(content)

        assert len(result) == 1
        assert result[0]["type"] == "function_call"
        assert result[0]["name"] == "test_func"
        assert result[0]["call_id"] == "call_789"
        assert result[0]["thought_signature"] == "test_signature"

    def test_function_response_content(self):
        """Convert Content with function response to Responses format."""
        content = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name="test_func",
                        id="call_789",
                        response={"result": "success"},
                    )
                )
            ],
        )
        result = content_to_responses(content)

        assert len(result) == 1
        assert result[0]["type"] == "function_call_output"
        assert result[0]["call_id"] == "call_789"
        assert result[0]["output"] == "success"


class TestToolsToGemini:
    """Test conversion of OpenAI tool format to Gemini format."""

    def test_empty_tools(self):
        """Empty tools list returns empty list."""
        result = tools_to_gemini([])
        assert result == []

    def test_single_function_tool(self):
        """Convert a single function tool."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                        },
                        "required": ["location"],
                    },
                },
            }
        ]
        result = tools_to_gemini(tools)

        assert len(result) == 1
        assert len(result[0].function_declarations) == 1

        decl = result[0].function_declarations[0]
        assert decl.name == "get_weather"
        assert decl.description == "Get weather for a location"

    def test_multiple_function_tools(self):
        """Convert multiple function tools."""
        tools = [
            {
                "type": "function",
                "function": {"name": "func1", "description": "First"},
            },
            {
                "type": "function",
                "function": {"name": "func2", "description": "Second"},
            },
        ]
        result = tools_to_gemini(tools)

        assert len(result) == 1  # All in one Tool object
        assert len(result[0].function_declarations) == 2

    def test_non_function_tools_ignored(self):
        """Non-function tools are ignored."""
        tools = [
            {"type": "other", "data": {}},
            {
                "type": "function",
                "function": {"name": "valid_func", "description": "Valid"},
            },
        ]
        result = tools_to_gemini(tools)

        assert len(result) == 1
        assert len(result[0].function_declarations) == 1
        assert result[0].function_declarations[0].name == "valid_func"


class TestThoughtSignatureRoundTrip:
    """Test that thought_signature survives conversion round-trip."""

    def test_roundtrip_preserves_thought_signature(self):
        """thought_signature should survive responses→contents→responses conversion."""
        original = [
            {
                "type": "function_call",
                "name": "test_func",
                "call_id": "call_abc",
                "arguments": '{"x": 1}',
                "thought_signature": "important_signature_data",
            }
        ]

        # Convert to google-genai format
        contents = responses_to_contents(original)

        # Verify signature is preserved in Content
        assert contents[0].parts[0].thought_signature == b"important_signature_data"

        # Convert back to Responses format
        result = content_to_responses(contents[0])

        # Verify signature survives round-trip
        assert result[0]["thought_signature"] == "important_signature_data"
