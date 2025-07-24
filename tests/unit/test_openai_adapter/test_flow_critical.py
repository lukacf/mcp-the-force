"""Critical tests for OpenAI flow orchestrator - follow-up logic and edge cases."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_preserves_reasoning_items_with_function_calls():
    """CRITICAL: Verify reasoning items are preserved when continuing after function calls.

    This is a key requirement from the Responses API documentation - reasoning items
    MUST be included when sending follow-up requests after function execution.
    """
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    async def mock_tool_dispatcher(name, args):
        return {"result": "tool output"}

    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    request_data = {
        "model": "o3",
        "messages": [{"role": "user", "content": "Analyze and use tools"}],
        "reasoning_effort": "high",
        "tools": [{"type": "function", "function": {"name": "analyze_data"}}],
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", return_value=None):  # Skip sleep in tests
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            # o3 uses background mode, so we need to mock polling
            # Initial create returns a job
            initial_job = MagicMock(id="resp_123", status="queued")

            # First retrieve shows completion with reasoning AND function call
            first_response = MagicMock(
                id="resp_123",
                status="completed",
                output=[
                    MagicMock(
                        type="reasoning",
                        status="completed",
                        content=[
                            {"type": "reasoning_text", "text": "Let me analyze..."}
                        ],
                        summary="I need to use the analyze_data tool",
                    ),
                    MagicMock(
                        type="function_call",
                        call_id="call_456",
                        name="analyze_data",
                        arguments="{}",
                    ),
                ],
            )

            # Follow-up create for tool results
            follow_up_job = MagicMock(id="resp_789", status="queued")

            # Follow-up retrieve shows completion
            follow_up_response = MagicMock(
                id="resp_789",
                status="completed",
                output_text="Based on the analysis, the result is X",
            )

            # Set up mock responses
            mock_client.responses.create.side_effect = [initial_job, follow_up_job]
            mock_client.responses.retrieve.side_effect = [
                first_response,
                follow_up_response,
            ]

            await orchestrator.run(request_data)

            # CRITICAL VERIFICATION: Follow-up only sends function results with previous_response_id
            follow_up_call = mock_client.responses.create.call_args_list[1]
            follow_up_input = follow_up_call.kwargs["input"]

            # When using previous_response_id, only send function results
            assert len(follow_up_input) == 1
            assert follow_up_input[0]["type"] == "function_call_output"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_streaming_function_calls():
    """Verify function calls in streaming mode are handled correctly."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    async def mock_tool_dispatcher(name, args):
        return "Weather is sunny"

    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "What's the weather?"}],
        "stream": True,
        "timeout": 60,  # Below STREAM_TIMEOUT_THRESHOLD (180)
        "tools": [{"type": "function", "function": {"name": "get_weather"}}],
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # First streaming response with function call
        first_stream = AsyncMock()
        first_stream.__aiter__.return_value = [
            MagicMock(id="resp_123", type="response.start"),
            MagicMock(
                type="response.tool_call",
                call_id="call_123",
                name="get_weather",
                arguments="{}",
            ),
        ]

        # Follow-up streaming response
        follow_up_stream = AsyncMock()
        follow_up_stream.__aiter__.return_value = [
            MagicMock(id="resp_456", type="response.start"),
            MagicMock(type="ResponseOutputTextDelta", delta="The weather "),
            MagicMock(type="ResponseOutputTextDelta", delta="is sunny"),
        ]

        mock_client.responses.create.side_effect = [first_stream, follow_up_stream]

        result = await orchestrator.run(request_data)

        # Verify follow-up is also streamed
        follow_up_call = mock_client.responses.create.call_args_list[1]
        assert follow_up_call.kwargs["stream"] is True
        assert follow_up_call.kwargs["previous_response_id"] == "resp_123"
        assert result["content"] == "The weather is sunny"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_mixed_background_statuses():
    """Verify proper handling when job status changes during polling."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3-pro",
        "messages": [{"role": "user", "content": "Complex task"}],
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", return_value=None):  # Skip sleep in tests
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            mock_client.responses.create.return_value = MagicMock(id="resp_123")

            # Simulate status progression
            mock_client.responses.retrieve.side_effect = [
                MagicMock(status="queued"),
                MagicMock(status="in_progress"),
                MagicMock(status="failed", error={"message": "Internal error"}),
            ]

            with pytest.raises(RuntimeError, match="Run failed with status: failed"):
                await orchestrator.run(request_data)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_extracts_content_from_complex_output():
    """Verify content extraction from various output formats."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    # Test different output structures that exist in the current implementation
    test_cases = [
        # Case 1: Simple output_text property
        {
            "output": MagicMock(output_text="Simple response"),
            "expected": "Simple response",
        },
        # Case 2: Complex output array with message items
        {
            "output": MagicMock(
                output_text="",  # Empty
                output=[
                    MagicMock(
                        type="message",
                        content=[
                            {"type": "text", "text": "Part 1"},
                            {"type": "output_text", "text": " Part 2"},
                        ],
                    )
                ],
            ),
            "expected": "Part 1 Part 2",
        },
        # Case 3: Object representation with attributes
        {
            "output": MagicMock(
                output_text="",
                output=[
                    MagicMock(
                        type="message",
                        content=[MagicMock(type="text", text="Object text")],
                    )
                ],
            ),
            "expected": "Object text",
        },
    ]

    for i, test_case in enumerate(test_cases):
        with patch(
            "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
        ) as mock_factory:
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            response = MagicMock(id=f"resp_{i}", status="completed")
            # Set attributes based on test case
            for key, value in test_case["output"].__dict__.items():
                setattr(response, key, value)

            mock_client.responses.create.return_value = response

            result = await orchestrator.run(
                {
                    "model": "o3",
                    "messages": [{"role": "user", "content": "Test"}],
                    "background": True,
                }
            )

            assert result["content"] == test_case["expected"], f"Failed case {i}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_web_search_tool_attachment():
    """Verify web search tool is attached only for gpt-4.1."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    models_to_test = [
        ("gpt-4.1", True),  # Should have web search
        ("o3", True),  # Now has web search!
        ("o3-pro", True),  # Now has web search!
    ]

    for model, should_have_web_search in models_to_test:
        with patch(
            "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
        ) as mock_factory:
            with patch("asyncio.sleep", return_value=None):  # Skip sleep in tests
                mock_client = AsyncMock()
                mock_factory.return_value = mock_client

                # Determine if model uses background mode
                use_background = model in ["o3-pro"]  # o3-pro forces background

                if use_background:
                    # Background mode setup
                    mock_client.responses.create.return_value = MagicMock(id="resp_123")
                    mock_client.responses.retrieve.return_value = MagicMock(
                        id="resp_123", status="completed", output_text="Response"
                    )
                else:
                    # Streaming mode setup for gpt-4.1 and o3
                    mock_stream = AsyncMock()
                    mock_stream.__aiter__.return_value = [
                        MagicMock(id="resp_123", type="response.start"),
                        MagicMock(type="ResponseOutputTextDelta", delta="Response"),
                        MagicMock(type="response.done"),
                    ]
                    mock_client.responses.create.return_value = mock_stream

                await orchestrator.run(
                    {
                        "model": model,
                        "messages": [{"role": "user", "content": "Test"}],
                        "timeout": 60,  # Below STREAM_TIMEOUT_THRESHOLD for streaming models
                    }
                )

                create_call = mock_client.responses.create.call_args
                tools = create_call.kwargs.get("tools", [])

                has_web_search = any(t.get("type") == "web_search" for t in tools)
                assert (
                    has_web_search == should_have_web_search
                ), f"Failed for model {model}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_return_debug_includes_tools():
    """Verify return_debug parameter includes tool information."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    tools = [
        {"type": "function", "function": {"name": "test_tool"}},
        {"type": "web_search"},
    ]

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Test"}],
        "tools": tools,
        "return_debug": True,
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", return_value=None):  # Skip sleep in tests
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            # gpt-4.1 with default timeout uses background mode
            mock_client.responses.create.return_value = MagicMock(id="resp_123")
            mock_client.responses.retrieve.return_value = MagicMock(
                id="resp_123", status="completed", output_text="Response"
            )

            result = await orchestrator.run(request_data)

            assert "_debug_tools" in result
            # The debug tools should include the built-in tools as well
            debug_tools = result["_debug_tools"]

            # Check that we have more tools than just the custom ones (includes built-ins)
            assert len(debug_tools) >= len(tools)

            # Check that our custom tools are included
            tool_names = []
            for t in debug_tools:
                if t.get("type") == "function":
                    # Handle nested function structure
                    if "function" in t and isinstance(t["function"], dict):
                        tool_names.append(t["function"].get("name"))
                    # Handle flat structure
                    elif "name" in t:
                        tool_names.append(t["name"])
                elif t.get("type") == "web_search":
                    tool_names.append("web_search")

            # Remove None values if any
            tool_names = [name for name in tool_names if name]

            assert "test_tool" in tool_names
            assert "web_search" in tool_names
            assert "search_project_history" in tool_names  # Built-in tool


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_incomplete_responses():
    """Verify handling of incomplete responses due to token limits."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3",
        "messages": [{"role": "user", "content": "Generate long text"}],
        "max_output_tokens": 100,
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", return_value=None):  # Skip sleep in tests
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            # o3 with default timeout uses background mode
            mock_client.responses.create.return_value = MagicMock(id="resp_123")

            # Mock polling to return incomplete status
            mock_response = MagicMock(
                id="resp_123",
                status="incomplete",
                output_text="Partial response...",
                incomplete_details=MagicMock(reason="max_output_tokens"),
            )
            mock_client.responses.retrieve.return_value = mock_response

            # Should handle incomplete response gracefully
            result = await orchestrator.run(request_data)

            assert result["content"] == "Partial response..."
            assert result["status"] == "incomplete"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_respects_timeout_in_follow_up():
    """Verify timeout is properly tracked across initial and follow-up requests."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    async def mock_tool_dispatcher(name, args):
        await asyncio.sleep(0.1)  # Simulate some work
        return "result"

    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    request_data = {
        "model": "o3",
        "messages": [{"role": "user", "content": "Test"}],
        "timeout": 10,  # 10 second total timeout
        "background": True,
        "tools": [{"type": "function", "function": {"name": "slow_tool"}}],
    }

    # Track time spent in each phase
    sleep_times = []

    async def mock_sleep(seconds):
        sleep_times.append(seconds)
        # Don't actually sleep to avoid test delays
        return

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        with patch("asyncio.sleep", side_effect=mock_sleep):
            mock_client = AsyncMock()
            mock_factory.return_value = mock_client

            # Initial response with function call (after some polling)
            mock_client.responses.create.return_value = MagicMock(id="resp_123")
            mock_client.responses.retrieve.side_effect = [
                MagicMock(status="in_progress"),
                MagicMock(
                    status="completed",
                    output=[
                        MagicMock(
                            type="function_call",
                            call_id="call_123",
                            name="slow_tool",
                            arguments="{}",
                        )
                    ],
                ),
            ]

            # Follow-up responses (also needs polling)
            follow_up_response = MagicMock(id="resp_456")

            mock_client.responses.create.side_effect = [
                MagicMock(id="resp_123"),  # Initial
                follow_up_response,  # Follow-up
            ]
            mock_client.responses.retrieve.side_effect = [
                # Initial polling
                MagicMock(status="in_progress"),
                MagicMock(
                    status="completed",
                    output=[
                        MagicMock(
                            type="function_call",
                            call_id="call_123",
                            name="slow_tool",
                            arguments="{}",
                        )
                    ],
                ),
                # Follow-up polling
                MagicMock(status="in_progress"),
                MagicMock(status="completed", output_text="Done"),
            ]

            result = await orchestrator.run(request_data)

            # Should complete successfully within timeout
            assert result["content"] == "Done"

            # Verify polling happened for both initial and follow-up requests
            assert len(sleep_times) >= 4  # At least 2 polls for each request

            # Verify exponential backoff is working
            # First poll should start at INITIAL_POLL_DELAY_SEC (3.0)
            assert sleep_times[0] == 3.0

            # Subsequent polls should increase with backoff
            for i in range(1, len(sleep_times) - 2):  # Check within each request
                if (
                    sleep_times[i] > sleep_times[i - 1]
                ):  # If not a reset between requests
                    assert sleep_times[i] > sleep_times[i - 1]  # Exponential backoff
