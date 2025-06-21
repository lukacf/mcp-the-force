"""
Internal integration tests.

These tests require MCP_ADAPTER_MOCK=1 to be set before importing any modules.
"""
import os

# Ensure MockAdapter is used for all internal tests
# This must be set before any imports of the mcp_second_brain modules
if os.getenv("MCP_ADAPTER_MOCK") != "1":
    # In CI, this should already be set, but for local development we set it here
    os.environ["MCP_ADAPTER_MOCK"] = "1"