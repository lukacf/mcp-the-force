"""Test that OpenAI adapter always uses Responses API."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mcp_second_brain.adapters.openai.client import OpenAIClientFactory


@pytest.mark.asyncio
async def test_client_uses_responses_api():
    """Verify that OpenAI client is created with use_responses_api=True."""
    # Clear any existing instances
    await OpenAIClientFactory.close_all()

    # Mock AsyncOpenAI to capture initialization parameters
    with patch("mcp_second_brain.adapters.openai.client.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client

        # Get client instance
        await OpenAIClientFactory.get_instance(api_key="test-key")

        # Verify AsyncOpenAI was called with use_responses_api=True
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args[1]

        assert "use_responses_api" in call_kwargs
        assert call_kwargs["use_responses_api"] is True
        assert call_kwargs["api_key"] == "test-key"

        # Cleanup
        await OpenAIClientFactory.close_all()


@pytest.mark.asyncio
async def test_responses_create_is_used():
    """Verify that flow strategies use client.responses.create()."""
    from mcp_second_brain.adapters.openai.flow import (
        BackgroundFlowStrategy,
        FlowContext,
    )
    from mcp_second_brain.adapters.openai.models import OpenAIRequest
    from mcp_second_brain.adapters.openai.tool_exec import ToolExecutor

    # Create mock client with responses.create
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.id = "resp_123"
    mock_response.status = "completed"
    mock_response.output_text = "Test response"
    mock_response.output = []

    # Set up the mock chain
    mock_client.responses.create = AsyncMock(return_value=mock_response)

    # Create flow context
    request = OpenAIRequest(
        model="o3", messages=[{"role": "user", "content": "Test"}], _api_key="test-key"
    )

    context = FlowContext(
        request=request,
        client=mock_client,
        tools=[],
        tool_executor=ToolExecutor(None),
        start_time=0,
        timeout_remaining=300,
    )

    # Execute background flow
    strategy = BackgroundFlowStrategy(context)
    result = await strategy.execute()

    # Verify responses.create was called (not chat.completions.create)
    mock_client.responses.create.assert_called_once()

    # Verify the call included correct parameters
    call_kwargs = mock_client.responses.create.call_args[1]
    assert call_kwargs["model"] == "o3"
    assert call_kwargs["input"] == [
        {"role": "user", "content": "Test"}
    ]  # messages -> input transformation
    assert call_kwargs["background"] is True

    # Verify result
    assert result["content"] == "Test response"
    assert result["response_id"] == "resp_123"


@pytest.mark.asyncio
async def test_reasoning_effort_format():
    """Verify reasoning_effort is passed as nested dict."""
    from mcp_second_brain.adapters.openai.flow import StreamingFlowStrategy, FlowContext
    from mcp_second_brain.adapters.openai.models import OpenAIRequest
    from mcp_second_brain.adapters.openai.tool_exec import ToolExecutor

    # Create mock client
    mock_client = AsyncMock()
    mock_stream = AsyncMock()

    # Mock the async iterator
    async def mock_iter(self):
        # Yield a response event
        event = MagicMock()
        event.id = "resp_456"
        event.type = "response.output_text"
        event.text = "Streamed response"
        yield event

    mock_stream.__aiter__ = mock_iter
    mock_client.responses.create = AsyncMock(return_value=mock_stream)

    # Create flow context with reasoning_effort
    request = OpenAIRequest(
        model="o3",
        messages=[{"role": "user", "content": "Test"}],
        reasoning_effort="low",
        _api_key="test-key",
    )

    context = FlowContext(
        request=request,
        client=mock_client,
        tools=[],
        tool_executor=ToolExecutor(None),
        start_time=0,
        timeout_remaining=300,
    )

    # Execute streaming flow
    strategy = StreamingFlowStrategy(context)
    result = await strategy.execute()

    # Verify responses.create was called with correct format
    mock_client.responses.create.assert_called_once()
    call_kwargs = mock_client.responses.create.call_args[1]

    # Check reasoning parameter is nested dict
    assert "reasoning" in call_kwargs
    assert call_kwargs["reasoning"] == {"effort": "low"}

    # Verify result
    assert result["content"] == "Streamed response"
    assert result["response_id"] == "resp_456"
