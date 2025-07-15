"""
Patch for OpenAI flow to make it cancellation-aware.
When the operation is cancelled, stop polling for the response.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

def patch_background_flow():
    """Patch BackgroundFlowStrategy to handle cancellation properly."""
    try:
        from mcp_second_brain.adapters.openai.flow import BackgroundFlowStrategy
        
        # Store original execute method
        original_execute = BackgroundFlowStrategy.execute
        
        async def cancellation_aware_execute(self):
            """Execute that stops polling when cancelled."""
            try:
                return await original_execute(self)
            except asyncio.CancelledError:
                logger.info(f"BackgroundFlowStrategy cancelled, stopping polling")
                # Don't try to return anything - just let the cancellation propagate
                raise
        
        # Replace the method
        BackgroundFlowStrategy.execute = cancellation_aware_execute
        logger.info("Patched BackgroundFlowStrategy for cancellation awareness")
        
    except Exception as e:
        logger.warning(f"Failed to patch BackgroundFlowStrategy: {e}")

# Apply patch when imported
patch_background_flow()