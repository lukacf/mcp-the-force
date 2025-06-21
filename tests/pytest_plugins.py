"""
Pytest plugin for early environment setup.

This ensures environment variables are set before any module imports happen.
"""
import os
import sys


def pytest_configure(config):
    """Configure pytest - runs before test collection."""
    # Determine which test suite we're running
    args = config.invocation_params.args
    
    # Check if we're running internal or MCP integration tests
    if any('tests/internal' in str(arg) for arg in args) or \
       any('tests/integration_mcp' in str(arg) for arg in args):
        # Set mock adapter environment variable
        os.environ["MCP_ADAPTER_MOCK"] = "1"
        
        # If adapters module was already imported, reload it
        if 'mcp_second_brain.adapters' in sys.modules:
            import importlib
            import mcp_second_brain.adapters
            
            # Clear adapter cache
            if hasattr(mcp_second_brain.adapters, '_ADAPTER_CACHE'):
                mcp_second_brain.adapters._ADAPTER_CACHE.clear()
            
            # Reload module to pick up MockAdapter
            importlib.reload(mcp_second_brain.adapters)


def pytest_collection_modifyitems(config, items):
    """Ensure fixtures are available across test directories."""
    # This helps with fixture discovery issues between directories
    pass