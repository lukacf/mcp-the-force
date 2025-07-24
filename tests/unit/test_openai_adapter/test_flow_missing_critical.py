"""Critical missing test cases identified by o3 review."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_preserves_reasoning_without_function_calls():
    """CRITICAL: Verify reasoning is preserved even when no function calls occur."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3",
        "messages": [{"role": "user", "content": "Explain quantum computing"}],
        "reasoning_effort": "high",
        "background": True,
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Response with reasoning but NO function calls
        mock_client.responses.create.return_value = MagicMock(id="resp_123")
        mock_client.responses.retrieve.return_value = MagicMock(
            status="completed",
            output=[
                MagicMock(
                    type="reasoning",
                    content=[
                        {
                            "type": "reasoning_text",
                            "text": "Let me think about quantum computing...",
                        }
                    ],
                    summary="Quantum computing uses quantum mechanics principles",
                ),
                MagicMock(
                    type="message",
                    content=[
                        {"type": "output_text", "text": "Quantum computing is..."}
                    ],
                ),
            ],
            output_text="Quantum computing is...",
        )

        result = await orchestrator.run(request_data)

        # Should return content without any follow-up calls
        assert result["content"] == "Quantum computing is..."
        assert mock_client.responses.create.call_count == 1  # No follow-up


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_incomplete_status():
    """Test handling of 'incomplete' status from OpenAI."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3",
        "messages": [{"role": "user", "content": "Test"}],
        "background": True,
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        mock_client.responses.create.return_value = MagicMock(id="resp_123")
        mock_client.responses.retrieve.return_value = MagicMock(
            status="incomplete",
            output_text="Partial response...",
            incomplete_details=MagicMock(reason="max_output_tokens"),
        )

        # Should handle gracefully, not raise error
        result = await orchestrator.run(request_data)
        assert result["content"] == "Partial response..."
        assert result.get("status") == "incomplete"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_cancelled_job():
    """Test handling when job is cancelled during polling."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "o3-pro",
        "messages": [{"role": "user", "content": "Test"}],
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        mock_client.responses.create.return_value = MagicMock(id="resp_123")
        mock_client.responses.retrieve.side_effect = [
            MagicMock(status="in_progress"),
            MagicMock(status="cancelled", error={"message": "User cancelled"}),
        ]

        with pytest.raises(RuntimeError, match="Run failed with status: cancelled"):
            await orchestrator.run(request_data)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_timeout_exceeded_in_follow_up():
    """Test that timeout budget is respected across initial and follow-up requests."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator
    from mcp_the_force.adapters.openai.errors import TimeoutException

    async def slow_tool_dispatcher(name, args):
        await asyncio.sleep(0.1)
        return "result"

    orchestrator = FlowOrchestrator(tool_dispatcher=slow_tool_dispatcher)

    request_data = {
        "model": "o3",
        "messages": [{"role": "user", "content": "Test"}],
        "timeout": 8,  # 8 second total timeout
        "background": True,
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Initial request takes 6 seconds
        mock_client.responses.create.return_value = MagicMock(id="resp_123")

        async def slow_initial_polling(*args):
            # First few polls are in_progress
            for _ in range(2):
                yield MagicMock(status="in_progress")
                await asyncio.sleep(3)  # 6 seconds total

            # Then return function call
            yield MagicMock(
                status="completed",
                output=[
                    MagicMock(
                        type="function_call",
                        call_id="call_1",
                        name="tool",
                        arguments="{}",
                    )
                ],
            )

        mock_client.responses.retrieve.side_effect = [
            MagicMock(status="in_progress"),
            MagicMock(status="in_progress"),
            MagicMock(
                status="completed",
                output=[
                    MagicMock(
                        type="function_call",
                        call_id="call_1",
                        name="tool",
                        arguments="{}",
                    )
                ],
            ),
        ]

        # Follow-up would exceed timeout
        follow_up_mock = MagicMock(id="resp_456")
        mock_client.responses.create.side_effect = [
            MagicMock(id="resp_123"),  # Initial
            follow_up_mock,  # Follow-up
        ]

        # Patch sleep to simulate time passing
        original_sleep = asyncio.sleep
        elapsed_time = 0

        async def mock_sleep(seconds):
            nonlocal elapsed_time
            elapsed_time += seconds
            if elapsed_time > 8:
                raise TimeoutException(
                    "Total timeout exceeded", elapsed=elapsed_time, timeout=8
                )
            await original_sleep(0.001)  # Small real delay for test

        with patch("asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(TimeoutException):
                await orchestrator.run(request_data)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_gateway_timeout_524():
    """Test handling of 524 gateway timeout (Cloudflare variant)."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator
    from mcp_the_force.adapters.openai.errors import GatewayTimeoutException

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {"model": "o3", "messages": [{"role": "user", "content": "Test"}]}

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Simulate 524 timeout
        api_error = Exception("Gateway timeout")
        api_error.status_code = 524
        mock_client.responses.create.side_effect = api_error

        with pytest.raises(GatewayTimeoutException) as exc_info:
            await orchestrator.run(request_data)

        assert exc_info.value.status_code == 524


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_empty_stream():
    """Test handling of empty streaming response."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Test"}],
        "stream": True,
        "timeout": 60,  # Force streaming mode
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Empty stream - only done event
        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = [
            MagicMock(id="resp_123", type="response.done")
        ]
        mock_client.responses.create.return_value = mock_stream

        result = await orchestrator.run(request_data)

        # Should return empty string, not None
        assert result["content"] == ""
        assert result["response_id"] == "resp_123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_response_id_in_later_event():
    """Test capturing response_id when it arrives after initial events."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Test"}],
        "stream": True,
        "timeout": 60,  # Force streaming mode
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Response ID comes after first delta
        # Need to ensure we don't have spurious response_id attributes on mocks
        class MinimalStream:
            def __init__(self, events):
                self._events = events

            async def __aiter__(self):
                for event in self._events:
                    yield event

        # Create events with specific attributes only
        event1 = MagicMock(spec=["type", "delta"])
        event1.type = "ResponseOutputTextDelta"
        event1.delta = "Hello"

        event2 = MagicMock(spec=["type", "id"])
        event2.type = "response.metadata"
        event2.id = "resp_789"

        event3 = MagicMock(spec=["type", "delta"])
        event3.type = "ResponseOutputTextDelta"
        event3.delta = " world"

        events = [event1, event2, event3]

        mock_client.responses.create.return_value = MinimalStream(events)

        result = await orchestrator.run(request_data)

        assert result["content"] == "Hello world"
        assert result["response_id"] == "resp_789"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_unknown_model_defaults_to_background():
    """Test that models without capabilities default to safe background mode."""
    from mcp_the_force.adapters.openai.flow import (
        FlowOrchestrator,
    )

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    request_data = {
        "model": "gpt-4.1",  # Known model
        "messages": [{"role": "user", "content": "Test"}],
        "stream": True,  # User wants streaming
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        mock_client.responses.create.return_value = MagicMock(
            id="resp_123", status="completed", output_text="Response"
        )

        # Temporarily remove model capabilities to simulate unknown model
        with patch("mcp_the_force.adapters.openai.flow.model_capabilities", {}):
            # Should use background mode when capabilities unavailable
            await orchestrator.run(request_data)

        # Verify background mode was used
        create_call = mock_client.responses.create.call_args
        assert create_call.kwargs["background"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_flow_handles_non_serializable_tool_result():
    """Test handling when tool returns non-JSON-serializable result."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    async def mock_tool_dispatcher(name, args):
        # Return non-serializable object
        return {"time": datetime.now(), "data": "test"}

    orchestrator = FlowOrchestrator(tool_dispatcher=mock_tool_dispatcher)

    request_data = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Test"}],
        "tools": [{"type": "function", "function": {"name": "get_time"}}],
        "timeout": 60,  # Force streaming mode
    }

    with patch(
        "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.return_value = mock_client

        # Setup streaming responses
        from .test_helpers import setup_streaming_flow_mocks

        stream_responses = [
            # First stream has function call
            [
                MagicMock(id="resp_123", type="response.start"),
                MagicMock(
                    type="response.tool_call",
                    call_id="call_1",
                    name="get_time",
                    arguments="{}",
                ),
            ],
            # Second stream has final response
            [
                MagicMock(id="resp_456", type="response.start"),
                MagicMock(type="ResponseOutputTextDelta", delta="Done"),
            ],
        ]

        setup_streaming_flow_mocks(mock_client, stream_responses)

        # Should handle serialization error gracefully
        result = await orchestrator.run(request_data)

        # Check that follow-up was called - tool result should be serialized
        assert mock_client.responses.create.call_count == 2
        assert result["content"] == "Done"


@pytest.mark.unit
async def test_flow_attachment_tool_only_with_vector_stores():
    """Test native file_search tool is only added when vector_store_ids present."""
    from mcp_the_force.adapters.openai.flow import FlowOrchestrator

    orchestrator = FlowOrchestrator(tool_dispatcher=AsyncMock())

    # Test with and without vector_store_ids
    test_cases = [
        ({"vector_store_ids": ["vs_123"]}, True),  # Should have file_search tool
        ({"vector_store_ids": None}, False),  # Should not have file_search tool
        ({}, False),  # No vector_store_ids at all
    ]

    for extra_params, should_have_file_search in test_cases:
        request_data = {
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "Test"}],
            **extra_params,
        }

        with patch(
            "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance"
        ) as mock_factory:
            with patch("asyncio.sleep", return_value=None):
                mock_client = AsyncMock()
                mock_factory.return_value = mock_client
                # Setup for background mode
                mock_client.responses.create.return_value = MagicMock(id="resp_123")
                mock_client.responses.retrieve.return_value = MagicMock(
                    id="resp_123", status="completed", output_text="Response"
                )

                await orchestrator.run(request_data)

            create_call = mock_client.responses.create.call_args
            tools = create_call.kwargs.get("tools", [])

            # Check for native file_search tool
            has_file_search_tool = any(t.get("type") == "file_search" for t in tools)

            assert has_file_search_tool == should_have_file_search
