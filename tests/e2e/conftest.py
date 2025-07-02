"""E2E test configuration and fixtures."""

import os
import pytest
import subprocess
import shlex
from pathlib import Path
import asyncio
import time
import json
import socket
from typing import List

# Set unique SESSION_DB_PATH per pytest-xdist worker to avoid SQLite locking
# This must be done before any imports that might use SessionCache
worker_id = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
os.environ["SESSION_DB_PATH"] = f"/tmp/e2e_sessions_{worker_id}.sqlite3"

# Cost guards removed - no longer needed

# Skip E2E tests if not explicitly enabled
if not os.getenv("CI_E2E"):
    pytest.skip("Skipping E2E tests - CI_E2E not set", allow_module_level=True)

# Check required environment variables
REQUIRED_ENV_VARS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
for var in REQUIRED_ENV_VARS:
    if not os.getenv(var):
        pytest.skip(f"Skipping E2E tests - {var} not set", allow_module_level=True)


def _free_port() -> int:
    """Get a free TCP port for this worker's MCP server."""
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture(scope="session")
def claude_config_path(tmp_path_factory):
    """
    Create an isolated Claude config *and* assign a unique TCP port
    for the MCP server spawned by this xdist worker.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    port = _free_port()  # -------- unique port
    os.environ["PORT"] = str(port)  # seen by 'uv run'
    # optional: for code clarity
    os.environ["MCP_PORT"] = str(port)

    home_dir = tmp_path_factory.mktemp(f"home_{worker}")
    os.environ["HOME"] = str(home_dir)
    xdg = home_dir / ".config"
    (xdg / "claude").mkdir(parents=True, exist_ok=True)
    os.environ["XDG_CONFIG_HOME"] = str(xdg)

    # 1. skeleton settings so onboarding never appears
    (home_dir / ".claude.json").write_text(json.dumps({"hasCompletedOnboarding": True}))
    (xdg / "claude" / "settings.json").write_text("{}")

    # 2. MCP config with our port baked in
    template_path = Path(__file__).parent / "claude-config.json"
    cfg = json.loads(template_path.read_text())
    cfg["mcpServers"]["second-brain"]["env"]["PORT"] = str(port)
    (xdg / "claude" / "config.json").write_text(json.dumps(cfg, indent=2))

    # 3. Extra environment hardening
    os.environ.update(
        {
            "CLAUDE_DISABLE_AUTO_UPDATE": "1",  # belt & braces
            "DISABLE_TELEMETRY": "1",  # keep logs clean
            "CI": "1",  # some prompts honour this
        }
    )

    return xdg, cfg


@pytest.fixture(autouse=True, scope="session")
def _verify_mcp_alive(claude_config_path):
    """
    Runs *once per worker* after the individual config is ready.
    Spawns Claude CLI, which in turn spawns the MCP server on the
    worker-specific port, and waits until it answers.
    """
    test_cmd = (
        "claude -p --dangerously-skip-permissions "
        '"Use the second-brain MCP server list_models tool"'
    )

    for attempt in range(20):  # ~40 s total
        proc = subprocess.run(
            test_cmd, shell=True, text=True, capture_output=True, env=os.environ
        )
        if proc.returncode == 0 and "model" in proc.stdout.lower():
            print(f"[{os.environ.get('PYTEST_XDIST_WORKER')}] MCP ready")
            return  # success
        time.sleep(2)

    pytest.exit(
        f"[{os.environ.get('PYTEST_XDIST_WORKER')}] MCP never became ready:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


@pytest.fixture
def claude_code(claude_config_path):
    """Run Claude CLI inside this worker's isolated env."""

    def _run(prompt: str, timeout: int = 300, output_format: str = "text") -> str:
        fmt = f"--output-format {output_format}" if output_format != "text" else ""
        cmd = f"claude -p --dangerously-skip-permissions {fmt} {shlex.quote(prompt)}"
        proc = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=os.environ,
        )
        if proc.returncode:
            raise RuntimeError(proc.stderr or proc.stdout)
        return proc.stdout

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
