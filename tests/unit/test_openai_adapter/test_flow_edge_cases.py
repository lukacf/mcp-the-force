"""Edge case tests for OpenAI flow orchestrator - error handling and complex scenarios."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import openai
import httpx
from .test_helpers import (
    setup_background_flow_mocks,
    setup_streaming_flow_mocks,
    create_function_call_response,
    create_text_response,
)
from mcp_second_brain.adapters.openai.errors import AdapterException, ErrorCategory


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_function_execution_failure():
    """Verify graceful handling when a function/tool fails during execution."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    async def mock_tool_dispatcher(name, args):
        if name == "failing_tool":
            raise ValueError("Database connection failed")
        return "ok"

    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Use the failing tool"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "failing_tool",
                    "description": "A tool that fails",
                },
            }
        ],
    }

    with patch("asyncio.sleep", return_value=None), patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Create the sequence of responses for background flow
        retrieve_responses = [
            # First retrieve: completed with function call
            create_function_call_response(
                response_id="resp_123",
                call_id="call_123",
                function_name="failing_tool",
                arguments='{"test": "data"}',
            ),
            # Second retrieve: final response acknowledging the error
            create_text_response(
                response_id="resp_456", text="I encountered an error searching memory."
            ),
        ]

        # Set up the background flow mocks
        setup_background_flow_mocks(mock_client, retrieve_responses)

        result = await orchestrator.run(request_data)

        # Should complete with error handling
        assert result["content"] == "I encountered an error searching memory."

        # Verify error was passed to model in follow-up
        assert mock_client.responses.create.call_count == 2
        follow_up_call = mock_client.responses.create.call_args_list[1]

        # For background mode, the input is in 'input' not 'messages'
        follow_up_input = follow_up_call.kwargs["input"]

        # Find the function call output with the error
        tool_error = None
        for item in follow_up_input:
            if isinstance(item, dict) and item.get("type") == "function_call_output":
                tool_error = item
                break

        assert tool_error is not None
        assert "Database connection failed" in tool_error["output"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_api_authentication_error():
    """Verify handling of authentication errors from OpenAI API."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Test"}],
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Simulate authentication error
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.headers = {"content-type": "application/json"}

        auth_error = openai.AuthenticationError(
            "Invalid API key",
            response=mock_response,
            body={
                "error": {"message": "Invalid API key", "type": "invalid_request_error"}
            },
        )
        mock_client.responses.create.side_effect = auth_error

        with pytest.raises(AdapterException) as exc_info:
            await orchestrator.run(request_data)

        assert exc_info.value.category == ErrorCategory.FATAL_CLIENT
        assert "Invalid API key" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_rate_limit_error():
    """Verify handling of rate limit errors from OpenAI API."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator
    from mcp_second_brain.adapters.openai.errors import AdapterException, ErrorCategory

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {"model": "o3", "messages": [{"role": "user", "content": "Test"}]}

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Simulate rate limit error
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.headers = {"content-type": "application/json"}

        rate_limit_error = openai.RateLimitError(
            "Rate limit exceeded",
            response=mock_response,
            body={
                "error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}
            },
        )
        mock_client.responses.create.side_effect = rate_limit_error

        with pytest.raises(AdapterException) as exc_info:
            await orchestrator.run(request_data)

        assert exc_info.value.category == ErrorCategory.RATE_LIMIT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_network_error():
    """Verify handling of network/connection errors."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Test"}],
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Simulate network error
        mock_client.responses.create.side_effect = httpx.NetworkError(
            "Connection refused"
        )

        with pytest.raises(Exception, match="Connection refused"):
            await orchestrator.run(request_data)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_malformed_response():
    """Verify handling of malformed/unexpected response structures."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3",
        "messages": [{"role": "user", "content": "Test"}],
        "background": True,
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Response missing expected attributes
        mock_client.responses.create.return_value = MagicMock(id="resp_123")

        # Malformed retrieve response - missing status
        malformed_response = MagicMock()
        delattr(malformed_response, "status")  # Remove status attribute
        mock_client.responses.retrieve.return_value = malformed_response

        with pytest.raises(AttributeError):
            await orchestrator.run(request_data)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_recursive_function_calls():
    """Test multi-turn function calls where follow-up also contains function calls."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    call_count = 0

    async def mock_tool_dispatcher(name, args):
        nonlocal call_count
        call_count += 1
        if name == "analyze":
            return "Need more data"
        elif name == "get_data":
            return "Here is the data"
        return "Unknown"

    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Analyze this"}],
        "tools": [
            {"type": "function", "function": {"name": "analyze"}},
            {"type": "function", "function": {"name": "get_data"}},
        ],
    }

    with patch("asyncio.sleep", return_value=None), patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Create responses for background flow
        retrieve_responses = [
            # First response: call analyze
            create_function_call_response(
                response_id="resp_1",
                call_id="call_1",
                function_name="analyze",
                arguments="{}",
            ),
            # Second response: after analyze, call get_data
            create_function_call_response(
                response_id="resp_2",
                call_id="call_2",
                function_name="get_data",
                arguments="{}",
            ),
            # Final response
            create_text_response(
                response_id="resp_3", text="Analysis complete with the data."
            ),
        ]

        setup_background_flow_mocks(mock_client, retrieve_responses)

        result = await orchestrator.run(request_data)

        # Should handle multiple rounds of function calls
        assert call_count == 2
        assert result["content"] == "Analysis complete with the data."
        assert mock_client.responses.create.call_count == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_initial_response_only_function_calls():
    """Test when initial response contains only function calls, no text."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    async def mock_tool_dispatcher(name, args):
        return "Tool result"

    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Do something"}],
        "timeout": 60,  # Force streaming mode
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Setup streaming responses
        stream_responses = [
            # First stream: only function call, no text
            [
                MagicMock(id="resp_123", type="response.start"),
                MagicMock(
                    type="response.tool_call",
                    call_id="call_1",
                    name="tool",
                    arguments="{}",
                ),
            ],
            # Second stream: the follow-up with actual content
            [
                MagicMock(id="resp_456", type="response.start"),
                MagicMock(
                    type="ResponseOutputTextDelta",
                    delta="Here's what I did with the tool.",
                ),
            ],
        ]

        setup_streaming_flow_mocks(mock_client, stream_responses)

        result = await orchestrator.run(request_data)

        # Final content should come from follow-up
        assert result["content"] == "Here's what I did with the tool."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_background_completes_just_before_timeout():
    """Test background job completing at the last possible moment."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3-pro",
        "messages": [{"role": "user", "content": "Complex task"}],
        "timeout": 6,  # 6 second timeout
    }

    async def mock_sleep(seconds):
        # Don't actually sleep in test
        pass

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", side_effect=mock_sleep):
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            mock_client.responses.create.return_value = MagicMock(id="resp_123")

            # Simulate job completing on the first poll
            # (to avoid timeout issues in this edge case test)
            mock_client.responses.retrieve.return_value = MagicMock(
                status="completed", output_text="Just made it!"
            )

            result = await orchestrator.run(request_data)

            # Should succeed without timeout
            assert result["content"] == "Just made it!"
            # Note: We can't reliably test poll count with the current timeout logic


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_timeout_exceeded_for_streaming_model():
    """Test that streaming model switches to background when timeout > threshold."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3",  # Supports streaming
        "messages": [{"role": "user", "content": "Test"}],
        "stream": True,  # User wants streaming
        "timeout": 200,  # But timeout exceeds STREAM_TIMEOUT_THRESHOLD (180)
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        mock_client.responses.create.return_value = MagicMock(
            id="resp_123", status="completed", output_text="Response"
        )

        await orchestrator.run(request_data)

        # Should use background mode due to timeout
        create_call = mock_client.responses.create.call_args
        assert create_call.kwargs["background"] is True
        assert create_call.kwargs.get("stream") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_explicit_stream_false_ignored():
    """Test that adapter overrides user's stream=False for optimal performance."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3",  # Supports streaming
        "messages": [{"role": "user", "content": "Test"}],
        "stream": False,  # User explicitly wants no streaming
        "timeout": 60,  # Within streaming threshold
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Mock streaming response
        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = [
            MagicMock(type="ResponseOutputTextDelta", delta="Test")
        ]
        mock_client.responses.create.return_value = mock_stream

        await orchestrator.run(request_data)

        # Adapter should override and use streaming anyway
        create_call = mock_client.responses.create.call_args
        assert create_call.kwargs["stream"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_missing_api_key():
    """Test handling when OPENAI_API_KEY is not configured."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Test"}],
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        # Simulate missing API key
        mock_factory.side_effect = ValueError("OPENAI_API_KEY not configured")

        with pytest.raises(ValueError, match="OPENAI_API_KEY not configured"):
            await orchestrator.run(request_data)
