"""
Configuration for internal integration tests.
"""
import os
import sys

# This must be set BEFORE any imports of mcp_second_brain modules
os.environ["MCP_ADAPTER_MOCK"] = "1"

# Force early setup to ensure MockAdapter is used
def pytest_configure(config):
    """Configure pytest - runs before test collection."""
    # Ensure MCP_ADAPTER_MOCK is set
    os.environ["MCP_ADAPTER_MOCK"] = "1"
    
    # If adapters module was already imported, we need to reload it
    if 'mcp_second_brain.adapters' in sys.modules:
        import importlib
        import mcp_second_brain.adapters
        # Clear any cached adapters
        if hasattr(mcp_second_brain.adapters, '_ADAPTER_CACHE'):
            mcp_second_brain.adapters._ADAPTER_CACHE.clear()
        # Reload to pick up MockAdapter
        importlib.reload(mcp_second_brain.adapters)