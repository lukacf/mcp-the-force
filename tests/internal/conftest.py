"""Shared fixtures for multi-turn conversation tests."""

import pytest
from unittest.mock import patch, AsyncMock


@pytest.fixture
def mock_memory_store():
    """Mock memory store to prevent real database writes."""
    with patch("mcp_the_force.history_store.store_conversation") as mock_store:
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
    from mcp_the_force.adapters.mock_adapter import MockAdapter
    import logging

    logger = logging.getLogger(__name__)

    # Clear MockAdapter's internal session storage
    MockAdapter._session_histories.clear()
    logger.debug("Cleared MockAdapter session histories")

    # Note: We don't clear the unified session cache database because
    # tests use unique session IDs, so there's no cross-contamination

    yield

    # No cleanup needed - sessions are isolated by unique IDs


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
