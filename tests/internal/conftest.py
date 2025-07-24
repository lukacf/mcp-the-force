"""Shared fixtures for multi-turn conversation tests."""

import pytest
from unittest.mock import patch, AsyncMock


@pytest.fixture
def mock_memory_store():
    """Mock memory store to prevent real database writes."""
    with patch("mcp_the_force.memory_store.store_conversation") as mock_store:
        mock_store.return_value = None
        yield mock_store


@pytest.fixture
def mock_vector_store():
    """Mock vector store creation."""
    with patch(
        "mcp_the_force.tools.vector_store_manager.VectorStoreManager"
    ) as mock_vs:
        mock_manager = AsyncMock()
        mock_manager.create = AsyncMock(return_value="mock-vector-store-id")
        mock_vs.return_value = mock_manager
        yield mock_manager


@pytest.fixture
async def clean_session_caches():
    """Clean all session caches before and after tests."""
    # Import here to avoid circular imports
    from mcp_the_force.gemini_session_cache import gemini_session_cache
    from mcp_the_force.grok_session_cache import grok_session_cache
    from mcp_the_force.session_cache import session_cache

    # Sessions are isolated by session_id, so we don't need to clear
    # Just ensure clean state by using unique session IDs

    yield

    # Close connections after test, ensuring all are attempted.
    # With the segfault fixed, we can handle potential errors gracefully.
    import logging

    logger = logging.getLogger(__name__)

    try:
        gemini_session_cache.close()
    except Exception as e:
        logger.error(f"Failed to close gemini_session_cache: {e}")

    try:
        grok_session_cache.close()
    except Exception as e:
        logger.error(f"Failed to close grok_session_cache: {e}")

    try:
        session_cache.close()
    except Exception as e:
        logger.error(f"Failed to close session_cache: {e}")


# Note: Removed track_tool_calls fixture - it's meaningless with MockAdapter
# MockAdapter doesn't make real decisions about tool usage.
# In real e2e tests, we would check the session history to see if tools were called
# since all tool calls are tracked as part of the conversation history.


@pytest.fixture
def session_id_generator():
    """Generate unique session IDs for tests."""
    counter = 0

    def generate():
        nonlocal counter
        counter += 1
        return f"test-session-{counter}"

    return generate
