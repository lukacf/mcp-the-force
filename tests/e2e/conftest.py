"""E2E test configuration and fixtures."""

import os
import json
import tempfile
import subprocess
from pathlib import Path
import asyncio
from typing import List
import pytest

# Set up environment BEFORE any MCP imports
wid = os.getenv("PYTEST_XDIST_WORKER", "gw0")
# Also need to set these in the actual os.environ for subprocess inheritance
os.environ["SESSION_DB_PATH"] = f"/tmp/e2e_sessions_{wid}.sqlite3"
os.environ["HOME"] = str(Path(tempfile.gettempdir()) / f"claude_home_{wid}")
os.environ["CLAUDE_HOME"] = os.environ["HOME"]
os.environ["CLAUDE_CONFIG_DIR"] = str(Path(os.environ["HOME"]) / ".config" / "claude")


# -----------------------------------------------------------------------------
# 1.  Create one private $HOME per xdist worker
# -----------------------------------------------------------------------------
def _build_worker_env() -> tuple[Path, dict]:
    wid = os.getenv("PYTEST_XDIST_WORKER", "gw0")  # gw0, gw1, …
    home = Path(tempfile.gettempdir()) / f"claude_home_{wid}"
    home.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()  # start from current env
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            # Claude Code also honours these two (see GitHub issues #1652/#519)
            "CLAUDE_HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(home / ".config" / "claude"),
            # Also need unique session DB
            "SESSION_DB_PATH": f"/tmp/e2e_sessions_{wid}.sqlite3",
        }
    )
    return home, env


_ISOLATED_HOME, _ENV = _build_worker_env()

# Import after environment setup
from mcp_second_brain.config import get_settings  # noqa: E402

# Clear settings cache to ensure fresh settings with new env vars
get_settings.cache_clear()

# prevent onboarding & create tool definition - always write to ensure it's current
config_file = _ISOLATED_HOME / ".claude.json"
config_file.write_text(json.dumps({"hasCompletedOnboarding": True}))

# Always write the config to ensure each worker gets correct SESSION_DB_PATH
cfg_dir = Path(_ENV["CLAUDE_CONFIG_DIR"])
cfg_dir.mkdir(parents=True, exist_ok=True)
(cfg_dir / "config.json").write_text(
    json.dumps(
        {
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
                        "SESSION_DB_PATH": _ENV["SESSION_DB_PATH"],
                    },
                    "timeoutMs": 180_000,
                }
            }
        },
        indent=2,
    )
)

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

    def _run(prompt: str, *, timeout: int = 300, output_format: str = "text") -> str:
        cmd = [
            "claude",
            "-p",
            "--dangerously-skip-permissions",
        ]
        if output_format != "text":
            cmd += ["--output-format", output_format]
        cmd.append(prompt)

        result = subprocess.run(
            cmd,  # no shell – fewer surprises
            env=_ENV,  # <-- the important part
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode:
            raise RuntimeError(
                f"Claude Code failed:\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"
            )
        return result.stdout

    return _run


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
