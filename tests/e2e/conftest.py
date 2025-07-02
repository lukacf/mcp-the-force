"""E2E test configuration and fixtures."""

import os
import json
import tempfile
import pytest
import subprocess
import shlex
from pathlib import Path
import asyncio
from typing import List

# ---------------------------------------------------------------------------
# Isolate every pytest-xdist worker
# ---------------------------------------------------------------------------
worker_id = os.environ.get("PYTEST_XDIST_WORKER", "gw0")

# unique SQLite DB so the MCP server instances never share the file
os.environ["SESSION_DB_PATH"] = f"/tmp/e2e_sessions_{worker_id}.sqlite3"

# unique HOME => unique ~/.claude.json
_isolated_home = Path(tempfile.gettempdir()) / f"claude_home_{worker_id}"
_isolated_home.mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(_isolated_home)  # ← this is what Claude uses

# build the tool definition once per worker (idempotent)
_config = _isolated_home / ".claude.json"
if not _config.exists():
    # Create skeleton settings to prevent onboarding
    _config.write_text(json.dumps({"hasCompletedOnboarding": True}))

    # Create MCP config
    _claude_dir = _isolated_home / ".config" / "claude"
    _claude_dir.mkdir(parents=True, exist_ok=True)

    tool_spec = {
        "mcpServers": {
            "second-brain": {
                "command": "uv",
                "args": ["run", "--", "mcp-second-brain"],
                "env": {
                    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                    "VERTEX_PROJECT": os.getenv("VERTEX_PROJECT", ""),
                    "VERTEX_LOCATION": os.getenv("VERTEX_LOCATION", ""),
                    "GOOGLE_APPLICATION_CREDENTIALS": os.getenv(
                        "GOOGLE_APPLICATION_CREDENTIALS", ""
                    ),
                    "MCP_ADAPTER_MOCK": "0",
                    "MEMORY_ENABLED": "true",
                    "SESSION_DB_PATH": os.environ["SESSION_DB_PATH"],
                },
                "timeoutMs": 180000,
            }
        }
    }

    # Write config atomically
    mcp_config = _claude_dir / "config.json"
    tmp = mcp_config.with_suffix(".tmp")
    tmp.write_text(json.dumps(tool_spec, indent=2))
    tmp.replace(mcp_config)

# Cost guards removed - no longer needed

# Skip E2E tests if not explicitly enabled
if not os.getenv("CI_E2E"):
    pytest.skip("Skipping E2E tests - CI_E2E not set", allow_module_level=True)

# Check required environment variables
REQUIRED_ENV_VARS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
for var in REQUIRED_ENV_VARS:
    if not os.getenv(var):
        pytest.skip(f"Skipping E2E tests - {var} not set", allow_module_level=True)


@pytest.fixture
def claude_code():
    """Helper to run Claude Code commands."""

    def run_command(
        prompt: str, timeout: int = 300, output_format: str = "text"
    ) -> str:
        """Run claude-code with given prompt."""
        format_flag = (
            f"--output-format {output_format}" if output_format != "text" else ""
        )
        cmd = f"claude -p --dangerously-skip-permissions {format_flag} {shlex.quote(prompt)}"

        # Each worker already has its own $HOME; no other isolation needed
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude Code failed: {result.stderr}\nSTDOUT: {result.stdout}"
            )

        return result.stdout

    return run_command


@pytest.fixture(scope="session")
def test_file(tmp_path_factory):
    """Create a test Python file for analysis."""
    test_dir = tmp_path_factory.mktemp("test-files")
    test_file = test_dir / "example.py"

    test_file.write_text("""
def fibonacci(n: int) -> int:
    '''Calculate the nth Fibonacci number.'''
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

def main():
    for i in range(10):
        print(f"F({i}) = {fibonacci(i)}")

if __name__ == "__main__":
    main()
""")

    return test_file


@pytest.fixture(scope="session")
def created_vector_stores():
    """Track vector stores created during tests for cleanup."""
    store_ids: List[str] = []
    yield store_ids

    # Cleanup after all tests
    if store_ids:
        from mcp_second_brain.tools.vector_store_manager import VectorStoreManager

        manager = VectorStoreManager()

        async def cleanup():
            for store_id in store_ids:
                try:
                    await manager.delete(store_id)
                    print(f"Cleaned up vector store: {store_id}")
                except Exception as e:
                    print(f"Failed to clean up vector store {store_id}: {e}")

        # Run cleanup
        asyncio.run(cleanup())
