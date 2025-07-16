"""
Patch for vertex adapter to make it cancellation-aware.
Note: With the async client.aio API, cancellation is handled natively by the httpx async client.
This file is kept for consistency but the patch is no longer necessary.
"""

import logging

logger = logging.getLogger(__name__)


def patch_vertex_adapter():
    """No-op patch - async client handles cancellation natively."""
    logger.info(
        "VertexAdapter now uses async client.aio API which handles cancellation natively"
    )


# Apply patch when imported
patch_vertex_adapter()
