"""Pytest plugins for MCP Second-Brain tests.

This file is automatically loaded by pytest and ensures environment variables
are set before any test modules are imported.
"""
import os
import sys
import importlib


def pytest_configure(config):
    """Set up environment variables before any test imports."""
    # Determine if we're running integration tests that need mocking
    args = " ".join(sys.argv)
    
    # Only set MCP_ADAPTER_MOCK if not already set
    if "MCP_ADAPTER_MOCK" not in os.environ:
        # Set MCP_ADAPTER_MOCK for internal and MCP integration tests
        if "tests/internal" in args or "tests/integration_mcp" in args:
            os.environ["MCP_ADAPTER_MOCK"] = "1"
            print(f"pytest_plugins: Set MCP_ADAPTER_MOCK=1 for integration tests")
        elif "tests/e2e" in args:
            # E2E tests should use real adapters
            os.environ["MCP_ADAPTER_MOCK"] = "0"
            print(f"pytest_plugins: Set MCP_ADAPTER_MOCK=0 for E2E tests")
    
    # If adapters module was already imported, reload it to pick up env var
    if 'mcp_second_brain.adapters' in sys.modules:
        # Clear the adapter cache first
        try:
            import mcp_second_brain.adapters
            if hasattr(mcp_second_brain.adapters, '_ADAPTER_CACHE'):
                mcp_second_brain.adapters._ADAPTER_CACHE.clear()
            if hasattr(mcp_second_brain.adapters, 'ADAPTER_REGISTRY'):
                # Force reload to pick up MockAdapter
                importlib.reload(mcp_second_brain.adapters)
        except Exception as e:
            print(f"pytest_plugins: Warning - could not reload adapters module: {e}")
    
    # Log the environment for debugging
    print(f"pytest_plugins: Running with args: {args}")
    print(f"pytest_plugins: MCP_ADAPTER_MOCK={os.environ.get('MCP_ADAPTER_MOCK', 'not set')}")


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--use-real-adapters",
        action="store_true",
        default=False,
        help="Use real adapters instead of mocks (for E2E tests)"
    )