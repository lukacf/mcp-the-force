"""E2E test configuration and fixtures."""

import os
import pytest
import subprocess
import shlex
from pathlib import Path
import asyncio
from typing import List

# Cost guards removed - no longer needed

# Skip E2E tests if not explicitly enabled
if not os.getenv("CI_E2E"):
    pytest.skip("Skipping E2E tests - CI_E2E not set", allow_module_level=True)

# Check required environment variables
REQUIRED_ENV_VARS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
for var in REQUIRED_ENV_VARS:
    if not os.getenv(var):
        pytest.skip(f"Skipping E2E tests - {var} not set", allow_module_level=True)


@pytest.fixture(scope="session")
def claude_config_path(tmp_path_factory):
    """Create Claude config in a temp directory."""
    xdg_config_home = tmp_path_factory.mktemp("config")
    claude_dir = xdg_config_home / "claude"
    claude_dir.mkdir()

    # Copy config template
    template_path = Path(__file__).parent / "claude-config.json"
    config_file = claude_dir / "config.json"
    config_file.write_text(template_path.read_text())

    return xdg_config_home


@pytest.fixture
def claude_code(claude_config_path):
    """Helper to run Claude Code commands."""

    def run_command(prompt: str, timeout: int = 300) -> str:
        """Run claude-code with given prompt."""
        cmd = f"claude -p --dangerously-skip-permissions {shlex.quote(prompt)}"

        env = os.environ.copy()
        env["XDG_CONFIG_HOME"] = str(claude_config_path)

        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env
        )

        if result.returncode != 0:
            raise RuntimeError(f"Claude Code failed: {result.stderr}")

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
