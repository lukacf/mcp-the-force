"""
Patch for grok adapter to make it cancellation-aware.
When the operation is cancelled, stop the API call and handle cleanup.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def patch_grok_adapter():
    """Patch GrokAdapter to handle cancellation properly."""
    try:
        from mcp_second_brain.adapters.grok.adapter import GrokAdapter

        # Store original generate method
        original_generate = GrokAdapter.generate

        async def cancellation_aware_generate(
            self, prompt, vector_store_ids=None, **kwargs
        ):
            """Generate that handles cancellation during API calls."""
            try:
                return await original_generate(self, prompt, vector_store_ids, **kwargs)
            except asyncio.CancelledError:
                logger.warning("[CANCEL] GrokAdapter generate cancelled")
                logger.info(
                    f"[CANCEL] Active tasks in Grok cancel handler: {len(asyncio.all_tasks())}"
                )
                logger.info("[CANCEL] Re-raising from Grok cancel_aware wrapper")
                # Don't try to return anything - just let the cancellation propagate
                raise

        # Replace the method
        GrokAdapter.generate = cancellation_aware_generate
        logger.debug("Patched GrokAdapter for cancellation awareness")

    except Exception as e:
        logger.warning(f"Failed to patch GrokAdapter: {e}")


# Apply patch when imported
patch_grok_adapter()
