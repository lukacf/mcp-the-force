"""
Configuration for MCP integration tests.
These tests use adapter-level mocking to test the MCP protocol interface.
"""

import pytest


# MCP_ADAPTER_MOCK should be set by the Makefile before pytest starts
# This ensures proper mock initialization


@pytest.fixture(scope="session", autouse=True)
def apply_mock_adapters():
    """Apply MockAdapter to all adapters for MCP integration tests."""
    from mcp_second_brain.adapters import ADAPTER_REGISTRY
    from mcp_second_brain.adapters.mock_adapter import MockAdapter

    # Replace all adapters with MockAdapter
    for name in list(ADAPTER_REGISTRY):
        ADAPTER_REGISTRY[name] = MockAdapter

    # Verify the mocking worked
    for name, adapter_class in ADAPTER_REGISTRY.items():
        if adapter_class is not MockAdapter:
            pytest.fail(
                f"Failed to mock adapter '{name}'. "
                f"Got {adapter_class} instead of MockAdapter."
            )


@pytest.fixture
async def mcp_server():
    """Create MCP server instance for testing."""
    # Import here to ensure MCP_ADAPTER_MOCK is set first
    from mcp_second_brain.server import mcp

    # Return the server instance
    return mcp
