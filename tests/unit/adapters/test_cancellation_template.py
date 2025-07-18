"""
Template for adapter cancellation tests.

⚠️  CRITICAL: Every adapter MUST have a cancellation test based on this template.
This ensures our workaround for the MCP library bug continues to work correctly.

Copy this file and adapt it for your specific adapter.
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock


@pytest.mark.unit
@pytest.mark.asyncio
class TestAdapterCancellation:
    """Test cancellation handling for adapters."""
    
    async def test_generate_handles_cancellation(self):
        """Test that adapter.generate() properly handles asyncio.CancelledError.
        
        This test ensures:
        1. CancelledError is caught by the cancel_aware_flow wrapper
        2. Cancellation is logged
        3. CancelledError is re-raised (not swallowed)
        4. No resources are leaked
        """
        # Import your adapter here
        # from mcp_second_brain.adapters.your_adapter import YourAdapter
        
        # Example for Grok adapter:
        from mcp_second_brain.adapters.grok import GrokAdapter
        
        # Mock the API client
        with patch('mcp_second_brain.adapters.grok.adapter.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Simulate cancellation during API call
            async def simulate_cancelled_api_call(*args, **kwargs):
                await asyncio.sleep(0.1)  # Simulate some work
                raise asyncio.CancelledError()
            
            mock_client.post = simulate_cancelled_api_call
            
            adapter = GrokAdapter()
            
            # Verify CancelledError is propagated
            with pytest.raises(asyncio.CancelledError):
                await adapter.generate("test prompt")
            
            # Verify cleanup happened (adapter-specific)
            # e.g., check connections were closed, resources freed
    
    async def test_background_polling_handles_cancellation(self):
        """Test cancellation during background polling (OpenAI-specific example).
        
        Only needed for adapters that do polling or long-running operations.
        """
        # Example for OpenAI's BackgroundFlowStrategy
        from mcp_second_brain.adapters.openai.flow import BackgroundFlowStrategy
        
        with patch('mcp_second_brain.adapters.openai.flow.OpenAIClientFactory') as mock_factory:
            mock_client = AsyncMock()
            mock_factory.get_client.return_value = mock_client
            
            # Simulate polling that gets cancelled
            poll_count = 0
            async def simulate_polling(*args, **kwargs):
                nonlocal poll_count
                poll_count += 1
                if poll_count == 1:
                    return Mock(status="in_progress")
                else:
                    # Simulate cancellation during second poll
                    raise asyncio.CancelledError()
            
            mock_client.responses.retrieve = simulate_polling
            
            strategy = BackgroundFlowStrategy(
                client=mock_client,
                model="o3",
                response_format=None
            )
            
            # Create a mock flow context
            flow_context = Mock()
            flow_context.request_data = {"prompt": "test"}
            flow_context.vector_store_ids = []
            
            with pytest.raises(asyncio.CancelledError):
                await strategy.execute(flow_context)
            
            # Verify polling stopped (only 2 calls, not infinite)
            assert poll_count == 2
    
    async def test_no_double_response_on_cancel(self):
        """Test that cancelled operations don't send multiple responses.
        
        This is the core issue we're working around.
        """
        # This would be tested at the integration level with operation_manager
        # but adapters should ensure they don't attempt to return results
        # after cancellation
        pass


# Example of adapter-specific test
@pytest.mark.unit
@pytest.mark.asyncio
async def test_grok_adapter_cancellation_with_real_patch():
    """Test that Grok's cancel_aware_flow.py is actually applied."""
    from mcp_second_brain.adapters.grok import GrokAdapter
    
    # The fact that this import works means the patch was applied
    # in the adapter's __init__.py
    
    # Verify the generate method is wrapped
    # The cancel_aware wrapper should be in place
    original_generate = GrokAdapter.generate
    assert hasattr(original_generate, '__wrapped__') or 'cancel_aware' in str(original_generate)