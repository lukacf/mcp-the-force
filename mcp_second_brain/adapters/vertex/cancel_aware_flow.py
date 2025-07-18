"""
Patch for vertex adapter - exists for consistency with other adapters.

IMPORTANT: This is part of our workaround for the MCP double-response bug.
When a client cancels a request:
1. MCP's RequestResponder.cancel() sends an error response
2. CancelledError propagates up to _handle_request
3. Without our patch, _handle_request would try to send ANOTHER response
4. This causes "Request already responded to" assertion and server crash

While Vertex's google-genai async client handles HTTP cancellation properly
and doesn't need method wrapping like Grok/OpenAI, we still need this file
to maintain consistency across all adapters. This ensures developers don't
forget to handle cancellation when adding new adapters.

The actual MCP bug fix is in patch_cancellation_handler.py which catches
CancelledError in _handle_request and returns early without double-responding.
"""

import logging

logger = logging.getLogger(__name__)


def patch_vertex_adapter():
    """No-op patch - Vertex's async client propagates CancelledError naturally.

    Unlike Grok/OpenAI adapters, Vertex doesn't need method wrapping because:
    - The google-genai client uses proper async/await patterns
    - CancelledError propagates cleanly without intervention
    - No custom polling loops that need explicit cancellation handling

    This file exists to maintain the pattern that ALL adapters must have
    cancel_aware_flow.py imported in their __init__.py.
    """
    logger.info(
        "VertexAdapter uses google-genai async client which propagates "
        "CancelledError correctly for MCP patch compatibility"
    )


# Apply patch when imported
patch_vertex_adapter()
