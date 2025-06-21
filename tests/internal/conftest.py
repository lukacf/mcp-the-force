"""
Configuration for internal integration tests.
"""
import os

# For local development, ensure MCP_ADAPTER_MOCK is set
# In CI, this is handled at the workflow level
if "MCP_ADAPTER_MOCK" not in os.environ:
    os.environ["MCP_ADAPTER_MOCK"] = "1"