"""Tests for the main OpenAI adapter."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from mcp_second_brain.adapters.openai import (
    OpenAIAdapter,
    AdapterException,
    ErrorCategory,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_adapter_simple_completion():
    """Test simple completion without tools."""
    with patch("mcp_second_brain.config.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = "test-key"
        adapter = OpenAIAdapter(model="gpt-4.1")

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", return_value=None):
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            # Mock streaming response
            mock_stream = AsyncMock()
            mock_stream.__aiter__.return_value = [
                MagicMock(id="resp_123", type="response.start"),
                MagicMock(type="ResponseOutputTextDelta", delta="Hello, "),
                MagicMock(type="ResponseOutputTextDelta", delta="world!"),
                MagicMock(type="response.done"),
            ]
            mock_client.responses.create.return_value = mock_stream

            result = await adapter.generate(
                prompt="Hello",
                messages=[{"role": "user", "content": "Hello"}],
                model="gpt-4.1",
                timeout=60,  # Use streaming mode
            )

            assert result["content"] == "Hello, world!"
            assert "response_id" in result  # Should have response ID


@pytest.mark.unit
@pytest.mark.asyncio
async def test_adapter_with_tools():
    """Test completion with tool usage."""
    with patch("mcp_second_brain.config.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = "test-key"
        adapter = OpenAIAdapter(model="gpt-4.1")

    async def mock_tool_dispatcher(name, args):
        if name == "get_weather":
            return {"temperature": 72, "conditions": "sunny"}
        return None

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", return_value=None):
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            # First response with tool call
            first_stream = AsyncMock()
            first_stream.__aiter__.return_value = [
                MagicMock(id="resp_123", type="response.start"),
                MagicMock(
                    type="response.tool_call",
                    call_id="call_456",
                    name="get_weather",
                    arguments='{"location": "SF"}',
                ),
            ]

            # Follow-up response
            follow_up_stream = AsyncMock()
            follow_up_stream.__aiter__.return_value = [
                MagicMock(id="resp_789", type="response.start"),
                MagicMock(
                    type="ResponseOutputTextDelta",
                    delta="The weather in SF is 72°F and sunny.",
                ),
                MagicMock(type="response.done"),
            ]

            mock_client.responses.create.side_effect = [first_stream, follow_up_stream]

            result = await adapter.generate(
                prompt="What's the weather?",
                messages=[{"role": "user", "content": "What's the weather?"}],
                model="gpt-4.1",
                tool_dispatcher=mock_tool_dispatcher,
                tools=[{"type": "function", "function": {"name": "get_weather"}}],
                timeout=60,
            )

            assert "72" in result["content"]
            assert "sunny" in result["content"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_adapter_o3_reasoning():
    """Test o3 model with reasoning preservation."""
    with patch("mcp_second_brain.config.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = "test-key"
        adapter = OpenAIAdapter(model="gpt-4.1")

    async def mock_tool_dispatcher(name, args):
        return {"result": "calculated"}

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", return_value=None):
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            # Background mode responses
            mock_client.responses.create.side_effect = [
                MagicMock(id="resp_123"),  # Initial
                MagicMock(id="resp_456"),  # Follow-up
            ]

            mock_client.responses.retrieve.side_effect = [
                # First poll shows reasoning + tool call
                MagicMock(
                    id="resp_123",
                    status="completed",
                    output=[
                        MagicMock(
                            type="reasoning",
                            content=[
                                {"type": "reasoning_text", "text": "Analyzing..."}
                            ],
                            summary="Need to calculate",
                        ),
                        MagicMock(
                            type="function_call",
                            call_id="call_789",
                            name="calculate",
                            arguments="{}",
                        ),
                    ],
                ),
                # Follow-up response
                MagicMock(
                    id="resp_456",
                    status="completed",
                    output_text="Based on the calculation, the answer is 42.",
                ),
            ]

            result = await adapter.generate(
                prompt="Calculate something complex",
                messages=[{"role": "user", "content": "Calculate something complex"}],
                model="o3",
                tool_dispatcher=mock_tool_dispatcher,
                tools=[{"type": "function", "function": {"name": "calculate"}}],
                reasoning_effort="high",
            )

            assert result["content"] == "Based on the calculation, the answer is 42."

            # Verify follow-up only sends function results
            follow_up_call = mock_client.responses.create.call_args_list[1]
            follow_up_input = follow_up_call.kwargs["input"]

            # When using previous_response_id, only send function results
            assert len(follow_up_input) == 1
            assert follow_up_input[0]["type"] == "function_call_output"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_adapter_error_handling():
    """Test error handling and categorization."""
    with patch("mcp_second_brain.config.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = "test-key"
        adapter = OpenAIAdapter(model="gpt-4.1")

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Mock an API error
        mock_client.responses.create.side_effect = Exception("API Error")

        with pytest.raises(AdapterException) as exc_info:
            await adapter.generate(
                prompt="Test",
                messages=[{"role": "user", "content": "Test"}],
                model="gpt-4.1",
            )

        assert exc_info.value.category == ErrorCategory.FATAL_CLIENT
        assert "Unexpected error" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_adapter_debug_mode():
    """Test return_debug includes tool information."""
    with patch("mcp_second_brain.config.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = "test-key"
        adapter = OpenAIAdapter(model="gpt-4.1")

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", return_value=None):
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            # Mock response
            mock_client.responses.create.return_value = MagicMock(id="resp_123")
            mock_client.responses.retrieve.return_value = MagicMock(
                id="resp_123", status="completed", output_text="Response"
            )

            tools = [{"type": "function", "function": {"name": "custom_tool"}}]

            result = await adapter.generate(
                prompt="Test",
                messages=[{"role": "user", "content": "Test"}],
                model="gpt-4.1",
                tools=tools,
                return_debug=True,
            )

            assert "_debug_tools" in result
            # Should include both custom and built-in tools
            tool_names = []
            for t in result["_debug_tools"]:
                if t.get("type") == "function":
                    # Handle both flat and nested structures
                    if "function" in t and "name" in t["function"]:
                        tool_names.append(t["function"]["name"])
                    elif "name" in t:
                        tool_names.append(t["name"])
                elif t.get("type") == "web_search":
                    tool_names.append("web_search")

            assert "custom_tool" in tool_names
            assert "web_search" in tool_names  # gpt-4.1 should have web search
            assert "search_project_history" in tool_names  # Built-in tool
