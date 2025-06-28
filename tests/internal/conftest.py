"""
Configuration for internal integration tests.
"""

import os
import tempfile

# Use a unique session DB per worker to avoid locking with pytest-xdist
os.environ.setdefault("SESSION_DB_PATH", os.path.join(tempfile.gettempdir(), f"test_sessions_{os.getpid()}.sqlite3"))

# Provide a dummy API key for adapters that require it
os.environ.setdefault("OPENAI_API_KEY", "dummy-key-for-mocks")

# For local development, ensure MCP_ADAPTER_MOCK is set
# In CI, this is handled at the workflow level
if "MCP_ADAPTER_MOCK" not in os.environ:
    os.environ["MCP_ADAPTER_MOCK"] = "1"

# Import tool definitions to ensure all tools are registered
import mcp_second_brain.tools.definitions  # noqa: F401
