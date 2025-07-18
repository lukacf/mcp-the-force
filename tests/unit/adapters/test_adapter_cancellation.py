"""Simplified cancellation tests for all adapters.

These tests verify that CancelledError propagates correctly through each adapter
to ensure compatibility with our MCP double-response bug workaround.
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, Mock, MagicMock


@pytest.mark.unit
@pytest.mark.asyncio
async def test_grok_adapter_propagates_cancellation():
    """Test that Grok adapter propagates CancelledError correctly."""
    with patch("mcp_second_brain.adapters.grok.adapter.get_settings") as mock_settings:
        mock_settings.return_value.xai.api_key = "test-key"

        with patch(
            "mcp_second_brain.adapters.grok.adapter.AsyncOpenAI"
        ) as mock_client_class:
            # Create a mock client that raises CancelledError
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Make chat.completions.create raise CancelledError
            async def raise_cancelled(*args, **kwargs):
                raise asyncio.CancelledError()

            mock_client.chat.completions.create = raise_cancelled

            from mcp_second_brain.adapters.grok import GrokAdapter

            adapter = GrokAdapter("grok-3-beta")

            # CancelledError should propagate
            with pytest.raises(asyncio.CancelledError):
                await adapter.generate("test prompt", model="grok-3-beta")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_adapter_propagates_cancellation():
    """Test that OpenAI adapter propagates CancelledError correctly."""
    with patch(
        "mcp_second_brain.adapters.openai.adapter.OpenAIClientFactory"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.get_client.return_value = mock_client

        # Make the orchestrator raise CancelledError
        with patch(
            "mcp_second_brain.adapters.openai.adapter.FlowOrchestrator"
        ) as mock_orchestrator_class:
            mock_orchestrator = AsyncMock()
            mock_orchestrator.run.side_effect = asyncio.CancelledError()
            mock_orchestrator_class.return_value = mock_orchestrator

            from mcp_second_brain.adapters.openai import OpenAIAdapter

            adapter = OpenAIAdapter()

            # CancelledError should propagate
            with pytest.raises(asyncio.CancelledError):
                await adapter.generate("test prompt", model="gpt-4")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vertex_adapter_propagates_cancellation():
    """Test that Vertex adapter propagates CancelledError correctly."""
    with patch("mcp_second_brain.adapters.vertex.adapter.genai") as mock_genai:
        # Mock the model to raise CancelledError
        mock_model = MagicMock()

        async def raise_cancelled(*args, **kwargs):
            raise asyncio.CancelledError()

        mock_model.generate_content_async = raise_cancelled
        mock_genai.GenerativeModel.return_value = mock_model

        from mcp_second_brain.adapters.vertex import VertexAdapter

        adapter = VertexAdapter(model="gemini-2.5-pro")

        # CancelledError should propagate naturally (no special handling needed)
        with pytest.raises(asyncio.CancelledError):
            await adapter.generate("test prompt")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_polling_stops_on_cancellation():
    """Test that OpenAI's polling stops when cancelled."""
    from mcp_second_brain.adapters.openai.flow import BackgroundFlowStrategy

    with patch(
        "mcp_second_brain.adapters.openai.flow.OpenAIClientFactory"
    ) as mock_factory:
        mock_client = AsyncMock()
        mock_factory.get_client.return_value = mock_client

        # Simulate a few polls then cancellation
        poll_count = 0

        async def mock_retrieve(*args, **kwargs):
            nonlocal poll_count
            poll_count += 1
            if poll_count < 3:
                return Mock(status="in_progress")
            else:
                raise asyncio.CancelledError()

        mock_client.responses.retrieve = mock_retrieve

        strategy = BackgroundFlowStrategy(
            client=mock_client, model="o3", response_format=None
        )

        flow_context = Mock()
        flow_context.request_data = {"prompt": "test"}
        flow_context.vector_store_ids = []

        with pytest.raises(asyncio.CancelledError):
            await strategy.execute(flow_context)

        # Should have polled a few times then stopped
        assert poll_count == 3


@pytest.mark.unit
def test_all_adapters_have_cancel_aware_flow():
    """Test that all adapters follow the cancel_aware_flow pattern."""
    # Import all adapters to verify their cancel_aware_flow is imported
    import mcp_second_brain.adapters.grok
    import mcp_second_brain.adapters.openai
    import mcp_second_brain.adapters.vertex

    # All should have the module imported (even if it's a no-op)
    assert hasattr(mcp_second_brain.adapters.grok, "cancel_aware_flow")
    assert hasattr(mcp_second_brain.adapters.openai, "cancel_aware_flow")
    assert hasattr(mcp_second_brain.adapters.vertex, "cancel_aware_flow")
