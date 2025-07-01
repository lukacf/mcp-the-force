"""
Configuration for internal integration tests.
"""

import os

# Set unique SESSION_DB_PATH per pytest-xdist worker to avoid SQLite locking
# This must be done before any imports that might use SessionCache
worker_id = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
os.environ["SESSION_DB_PATH"] = f"/tmp/e2e_sessions_{worker_id}.sqlite3"

# For local development, ensure MCP_ADAPTER_MOCK is set
# In CI, this is handled at the workflow level
if "MCP_ADAPTER_MOCK" not in os.environ:
    os.environ["MCP_ADAPTER_MOCK"] = "1"

# Import tool definitions to ensure all tools are registered
import mcp_second_brain.tools.definitions  # noqa: F401, E402
