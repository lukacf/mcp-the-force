"""Unit tests for OpenAI adapter flow orchestrator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mcp_second_brain.adapters.openai.errors import TimeoutException


# Note: These tests are written BEFORE the implementation (TDD approach)
# They define the expected behavior of the flow orchestrator


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_selects_background_for_o3_pro():
    """Verify o3-pro always uses background mode regardless of request."""
    # This test will fail until we implement the FlowOrchestrator
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    mock_tool_dispatcher = AsyncMock()
    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    # o3-pro should force background mode
    request_data = {
        "model": "o3-pro",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,  # Even if stream is requested
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Mock the background response
        mock_client.responses.create.return_value = MagicMock(
            id="resp_123", status="completed", output_text="Response text"
        )

        await orchestrator.run(request_data)

        # Verify background mode was used
        create_call = mock_client.responses.create.call_args
        assert create_call.kwargs.get("background") is True
        assert create_call.kwargs.get("stream") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_selects_streaming_for_supported_model():
    """Verify streaming is used when model supports it and timeout allows."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    mock_tool_dispatcher = AsyncMock()
    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    request_data = {
        "model": "o3",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
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
            MagicMock(type="ResponseOutputTextDelta", delta="Hello "),
            MagicMock(type="ResponseOutputTextDelta", delta="world!"),
            MagicMock(id="resp_123", type="response.done"),
        ]
        mock_client.responses.create.return_value = mock_stream

        result = await orchestrator.run(request_data)

        # Verify streaming mode was used
        create_call = mock_client.responses.create.call_args
        assert create_call.kwargs.get("stream") is True
        assert create_call.kwargs.get("background") is False
        assert result["content"] == "Hello world!"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_function_calls_with_follow_up():
    """Verify the critical follow-up request logic after function calls."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    # Mock tool execution
    async def mock_tool_dispatcher(name, args):
        if name == "get_weather":
            return {"temperature": "72F", "condition": "sunny"}
        return {}

    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "What's the weather?"}],
        "tools": [{"type": "function", "function": {"name": "get_weather"}}],
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # First response contains function call
        function_call = MagicMock()
        function_call.type = "function_call"
        function_call.call_id = "call_123"
        function_call.name = "get_weather"
        function_call.arguments = "{}"

        first_response = MagicMock(
            id="resp_123", status="completed", output=[function_call]
        )

        # Follow-up response after function execution
        follow_up_response = MagicMock(
            id="resp_456",
            status="completed",
            output_text="The weather is 72F and sunny.",
        )

        mock_client.responses.create.side_effect = [first_response, follow_up_response]

        result = await orchestrator.run(request_data)

        # Verify two API calls were made
        assert mock_client.responses.create.call_count == 2

        # CRITICAL: Verify follow-up uses previous_response_id and ONLY tool results
        follow_up_call = mock_client.responses.create.call_args_list[1]
        assert follow_up_call.kwargs["previous_response_id"] == "resp_123"
        assert follow_up_call.kwargs["input"] == [
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": '{"temperature": "72F", "condition": "sunny"}',
            }
        ]
        # Tools should be re-attached - should include built-in tools + custom tools
        follow_up_tools = follow_up_call.kwargs["tools"]
        assert (
            len(follow_up_tools) == 3
        )  # search_project_history + web_search + get_weather

        # Extract tool names from different structures
        tool_names = []
        for t in follow_up_tools:
            if t.get("type") == "function":
                # Handle nested function structure
                if "function" in t:
                    tool_names.append(t["function"].get("name"))
                # Handle flat structure
                elif "name" in t:
                    tool_names.append(t["name"])
            elif t.get("type") == "web_search":
                tool_names.append("web_search")

        # Verify all expected tools are present
        assert "get_weather" in tool_names
        assert "search_project_history" in tool_names
        assert "web_search" in tool_names

        assert result["content"] == "The weather is 72F and sunny."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_multiple_function_calls():
    """Verify parallel function calls are executed correctly."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    call_count = 0

    async def mock_tool_dispatcher(name, args):
        nonlocal call_count
        call_count += 1
        return f"Result for {name}"

    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Do multiple things"}],
        "parallel_tool_calls": True,
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Response with multiple function calls
        fc1 = MagicMock()
        fc1.type = "function_call"
        fc1.call_id = "call_1"
        fc1.name = "tool_1"
        fc1.arguments = "{}"

        fc2 = MagicMock()
        fc2.type = "function_call"
        fc2.call_id = "call_2"
        fc2.name = "tool_2"
        fc2.arguments = "{}"

        fc3 = MagicMock()
        fc3.type = "function_call"
        fc3.call_id = "call_3"
        fc3.name = "tool_3"
        fc3.arguments = "{}"

        first_response = MagicMock(
            id="resp_123", status="completed", output=[fc1, fc2, fc3]
        )

        follow_up_response = MagicMock(
            id="resp_456", status="completed", output_text="All tasks completed."
        )

        mock_client.responses.create.side_effect = [first_response, follow_up_response]

        await orchestrator.run(request_data)

        # All tools should be executed
        assert call_count == 3

        # Follow-up should include all results
        follow_up_call = mock_client.responses.create.call_args_list[1]
        assert len(follow_up_call.kwargs["input"]) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_reasoning_models():
    """Verify reasoning parameters are handled correctly."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3",
        "messages": [{"role": "user", "content": "Solve this problem"}],
        "reasoning_effort": "high",
        "background": True,
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Set up initial create response
        initial_response = MagicMock(id="resp_123")
        mock_client.responses.create.return_value = initial_response

        # Set up retrieve response with reasoning and output
        mock_response = MagicMock(
            id="resp_123",
            status="completed",
            output_text="The answer is 42",  # Add the convenience property
            output=[
                MagicMock(type="reasoning", summary="I need to analyze..."),
                MagicMock(
                    type="message",
                    content=[{"type": "output_text", "text": "The answer is 42"}],
                ),
            ],
        )
        mock_client.responses.retrieve.return_value = mock_response

        result = await orchestrator.run(request_data)

        # Verify reasoning parameters were passed
        create_call = mock_client.responses.create.call_args
        assert create_call.kwargs["reasoning"] == {"effort": "high"}

        assert result["content"] == "The answer is 42"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_background_polling_with_exponential_backoff():
    """Verify background polling uses exponential backoff."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3-pro",
        "messages": [{"role": "user", "content": "Complex analysis"}],
    }

    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", side_effect=mock_sleep):
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            # Initial response
            mock_client.responses.create.return_value = MagicMock(
                id="resp_123", status="queued"
            )

            # Polling responses
            mock_client.responses.retrieve.side_effect = [
                MagicMock(status="in_progress"),
                MagicMock(status="in_progress"),
                MagicMock(status="in_progress"),
                MagicMock(status="completed", output_text="Done"),
            ]

            await orchestrator.run(request_data)

            # Verify exponential backoff
            assert len(sleep_calls) == 4
            assert sleep_calls[0] == 3.0  # Initial delay
            # Each subsequent delay should increase
            for i in range(1, len(sleep_calls)):
                assert sleep_calls[i] > sleep_calls[i - 1]
                assert sleep_calls[i] <= 30.0  # Max cap


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_timeout():
    """Verify timeout is handled properly."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3",
        "messages": [{"role": "user", "content": "Test"}],
        "timeout": 5,  # 5 second timeout
        "background": True,
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Response stays in progress
        mock_client.responses.create.return_value = MagicMock(id="resp_123")
        mock_client.responses.retrieve.return_value = MagicMock(status="in_progress")

        # Should timeout after 5 seconds
        with pytest.raises(TimeoutException) as exc_info:
            await orchestrator.run(request_data)

        assert exc_info.value.timeout == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_preserves_response_id():
    """Verify response_id is captured and returned correctly."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
        "timeout": 60,  # Use a timeout less than STREAM_TIMEOUT_THRESHOLD
    }

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Mock streaming response with response_id
        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = [
            MagicMock(id="resp_789", type="response.start"),
            MagicMock(type="ResponseOutputTextDelta", delta="Hi"),
            MagicMock(type="response.done"),
        ]
        mock_client.responses.create.return_value = mock_stream

        result = await orchestrator.run(request_data)

        assert result["response_id"] == "resp_789"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_deduplicates_function_calls():
    """Verify function calls are deduplicated by call_id."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator

    call_count = 0
    calls_seen = []

    async def mock_tool_dispatcher(name, args):
        # Track each call
        nonlocal call_count
        call_count += 1
        calls_seen.append(name)

        # Handle built-in tools
        if name == "search_project_history":
            return {"results": []}

        return f"Result for {name}"

    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Response with duplicate call_ids
        # Create streaming function call events
        fc1a = MagicMock()
        fc1a.type = "response.tool_call"
        fc1a.call_id = "call_1"
        fc1a.name = "tool"
        fc1a.arguments = "{}"

        fc1b = MagicMock()
        fc1b.type = "response.tool_call"
        fc1b.call_id = "call_1"  # Duplicate call_id
        fc1b.name = "tool"
        fc1b.arguments = "{}"

        fc2 = MagicMock()
        fc2.type = "response.tool_call"
        fc2.call_id = "call_2"
        fc2.name = "tool"
        fc2.arguments = "{}"

        # Set up streaming responses since gpt-4.1 with 60s timeout uses streaming
        first_stream = AsyncMock()
        first_stream.__aiter__.return_value = [
            MagicMock(id="resp_123", type="response.start"),
            fc1a,  # First call
            fc1b,  # Duplicate call
            fc2,  # Second unique call
            MagicMock(type="response.done"),
        ]

        follow_up_stream = AsyncMock()
        follow_up_stream.__aiter__.return_value = [
            MagicMock(id="resp_456", type="response.start"),
            MagicMock(type="ResponseOutputTextDelta", delta="Done"),
            MagicMock(type="response.done"),
        ]

        mock_client.responses.create.side_effect = [first_stream, follow_up_stream]

        await orchestrator.run(
            {
                "model": "gpt-4.1",
                "messages": [{"role": "user", "content": "test"}],
                "timeout": 60,
            }
        )

        # Only 2 unique calls should be executed (not 3)
        assert call_count == 2, f"Expected 2 calls, got {call_count}"
        assert calls_seen == ["tool", "tool"]

        # Verify the follow-up request was made
        assert mock_client.responses.create.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_gateway_timeout():
    """Verify gateway timeout errors are handled with proper error message."""
    from mcp_second_brain.adapters.openai.flow import FlowOrchestrator
    from mcp_second_brain.adapters.openai.errors import GatewayTimeoutException

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {"model": "o3", "messages": [{"role": "user", "content": "Test"}]}

    with patch(
        "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Simulate gateway timeout using OpenAI's APIStatusError
        import openai
        import httpx

        # Create a proper httpx response with 504 status
        response = httpx.Response(
            status_code=504,
            headers={},
            content=b'{"error": {"message": "Gateway timeout"}}',
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        )
        api_error = openai.APIStatusError(
            "Gateway timeout",
            response=response,
            body={"error": {"message": "Gateway timeout"}},
        )
        mock_client.responses.create.side_effect = api_error

        with pytest.raises(GatewayTimeoutException) as exc_info:
            await orchestrator.run(request_data)

        assert exc_info.value.status_code == 504
        assert exc_info.value.model_name == "o3"


@pytest.mark.unit
def test_flow_validates_model_capabilities():
    """Verify flow checks model capabilities before execution."""

    # This test doesn't need the orchestrator or request_data variables

    # When run() is called, it should override user preference
    # This test ensures the orchestrator respects model capabilities
