"""
Configuration for MCP integration tests.
These tests use adapter-level mocking to test the MCP protocol interface.
"""
import os
import pytest

# Configure anyio to only use asyncio backend (not trio)
def pytest_configure(config):
    """Configure pytest-anyio to only use asyncio backend."""
    # This prevents "ModuleNotFoundError: No module named 'trio'" errors
    config.option.anyio_backends = ["asyncio"]

# For local development, ensure MCP_ADAPTER_MOCK is set
# In CI, this is handled at the workflow level
if "MCP_ADAPTER_MOCK" not in os.environ:
    os.environ["MCP_ADAPTER_MOCK"] = "1"


@pytest.fixture(scope="session", autouse=True)
def verify_mock_adapter():
    """Verify that MockAdapter is enabled for MCP integration tests."""
    # Verify the adapter was actually injected
    from mcp_second_brain.adapters import ADAPTER_REGISTRY
    from mcp_second_brain.adapters.mock_adapter import MockAdapter
    
    for name, adapter_class in ADAPTER_REGISTRY.items():
        if adapter_class is not MockAdapter:
            pytest.fail(
                f"Adapter '{name}' is not using MockAdapter! "
                f"Got {adapter_class} instead. "
                "This suggests MCP_ADAPTER_MOCK was set too late."
            )


@pytest.fixture
async def mcp_server():
    """Create MCP server instance for testing."""
    # Import here to ensure MCP_ADAPTER_MOCK is set first
    from mcp_second_brain.server import mcp
    
    # Return the server instance
    return mcp