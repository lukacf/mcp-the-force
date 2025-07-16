"""Configuration for e2e multi-turn tests with real API calls.

WARNING: These tests make real API calls and incur costs. They should be run
sparingly and only when verifying actual model behavior is critical.
"""

import pytest
import os
from typing import Dict, List
from unittest.mock import patch


@pytest.fixture(scope="session")
def real_api_setup():
    """Ensure real API keys are available for e2e tests."""
    # Check for API keys - fail fast if not configured
    from mcp_second_brain.config import get_settings

    settings = get_settings()

    required_keys = {
        "OpenAI": settings.openai_api_key,
        "Vertex Project": settings.vertex_project,
    }

    missing = [k for k, v in required_keys.items() if not v]
    if missing:
        pytest.skip(f"E2E tests require API keys: {missing}")

    # Ensure NOT using mock adapter
    if os.environ.get("MCP_ADAPTER_MOCK") == "1":
        del os.environ["MCP_ADAPTER_MOCK"]

    yield

    # Cleanup any test data if needed


@pytest.fixture
def track_tool_calls():
    """Track actual tool calls made during e2e tests.

    This patches the tool implementations to log when they're called,
    allowing us to verify models use conversation history instead of tools.
    """
    tool_calls: Dict[str, List[Dict]] = {
        "search_project_memory": [],
        "search_session_attachments": [],
    }

    async def mock_search_memory(*args, **kwargs):
        tool_calls["search_project_memory"].append({"args": args, "kwargs": kwargs})
        # Return a marker that we can detect in responses
        return "E2E_TEST_TOOL_MARKER: search_project_memory was called"

    async def mock_search_attachments(*args, **kwargs):
        tool_calls["search_session_attachments"].append(
            {"args": args, "kwargs": kwargs}
        )
        return "E2E_TEST_TOOL_MARKER: search_session_attachments was called"

    with (
        patch(
            "mcp_second_brain.tools.search_memory.SearchMemoryAdapter.generate",
            mock_search_memory,
        ),
        patch(
            "mcp_second_brain.tools.search_attachments.SearchAttachmentAdapter.generate",
            mock_search_attachments,
        ),
    ):
        yield tool_calls


@pytest.fixture
def unique_marker_generator():
    """Generate unique markers for e2e tests that won't exist in project memory."""
    import uuid
    import time

    def generate():
        # Use timestamp + UUID to ensure uniqueness
        timestamp = int(time.time() * 1000)
        unique_id = str(uuid.uuid4())[:8]
        return f"E2E_TEST_{timestamp}_{unique_id}"

    return generate


@pytest.fixture(autouse=True)
async def cleanup_test_sessions():
    """Clean up any test sessions after each test."""
    yield

    # Import here to avoid circular imports

    # Clear test sessions (those starting with specific prefixes)
    # Note: In production, you'd implement a more sophisticated cleanup
    # that only removes test data


@pytest.fixture
def e2e_test_timeout():
    """Timeout for e2e tests (some models like o3-pro can take minutes)."""
    return 300  # 5 minutes


# Mark all tests in this directory as e2e
def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.e2e)
        item.add_marker(pytest.mark.slow)
