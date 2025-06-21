"""Fixtures for MCP integration tests."""
import os
import pytest

# Set mock mode for all integration tests
os.environ["MCP_MOCK"] = "1"


@pytest.fixture
def anyio_backend():
    """Use only asyncio backend for tests."""
    return "asyncio"


@pytest.fixture
def mcp_server():
    """Get the MCP server instance."""
    # Import triggers tool registration
    from mcp_second_brain import server
    return server.mcp