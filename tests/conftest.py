"""
Shared test fixtures and configuration for MCP Second-Brain tests.
"""

# Note: Test isolation is now handled automatically in config.py
# When pytest is detected and no explicit config files are set,
# default config.yaml/secrets.yaml files are skipped
import os

import sys
from pathlib import Path
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, Mock, AsyncMock, patch
import asyncio
import time
import contextlib

# Note: Adapter mocking is controlled by MCP_ADAPTER_MOCK environment variable

# Note: Adapter mocking is controlled per test suite:
# - Unit tests: Don't need mocking (pure Python)
# - Internal tests: Use adapter mocking (MCP_ADAPTER_MOCK=1 set before Python starts)
# - MCP integration tests: Use adapter mocking (MCP_ADAPTER_MOCK=1 set before Python starts)
# - E2E tests: Use real adapters (MCP_ADAPTER_MOCK=0)
#
# IMPORTANT: MCP_ADAPTER_MOCK must be set before any imports happen.
# For local testing, run: MCP_ADAPTER_MOCK=1 pytest tests/internal

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def verify_mock_adapter_for_integration():
    """Verify MockAdapter is properly activated for integration tests."""
    # Only check if we're in internal, MCP integration, or multi-turn tests
    if any(
        arg
        for arg in sys.argv
        if "tests/internal" in arg
        or "tests/integration_mcp" in arg
        or "tests/integration/multi_turn" in arg
    ):
        if os.getenv("MCP_ADAPTER_MOCK") != "1":
            pytest.fail(
                "FATAL: MCP_ADAPTER_MOCK=1 must be set in the environment *before* running pytest.\n"
                "For example: MCP_ADAPTER_MOCK=1 pytest tests/internal"
            )

        # Clear instance cache to prevent state leakage between tests
        try:
            from mcp_second_brain.adapters import _ADAPTER_CACHE

            _ADAPTER_CACHE.clear()
            # Use print since logger might not be configured yet in test setup
            print("INFO: Cleared adapter cache for integration tests")
        except ImportError:
            pass  # If we can't import, tests will fail for other reasons


@pytest.fixture
def mock_env(monkeypatch):
    """Set up test environment variables."""
    # Clear the cached settings first
    from mcp_second_brain.config import get_settings

    get_settings.cache_clear()

    test_env = {
        "OPENAI_API_KEY": "test-openai-key",
        "XAI_API_KEY": "test-xai-key",
        "VERTEX_PROJECT": "test-project",
        "VERTEX_LOCATION": "us-central1",
        "CONTEXT_PERCENTAGE": "0.85",
        "LOG_LEVEL": "WARNING",  # Reduce noise in tests
    }
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)

    # Clear cache again to force reload with new env
    get_settings.cache_clear()

    return test_env


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project structure for testing."""
    # Create basic project structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("# Main file\nprint('hello')")
    (tmp_path / "src" / "utils.py").write_text("# Utils\ndef helper(): pass")

    # Create a .gitignore
    (tmp_path / ".gitignore").write_text("*.log\n__pycache__/\n.env")

    # Create some ignored files
    (tmp_path / "debug.log").write_text("Log content")
    (tmp_path / "src" / "__pycache__").mkdir()

    return tmp_path


@pytest.fixture
def mock_openai_client():
    """Mock AsyncOpenAI client conforming to Responses API."""
    mock = MagicMock()

    # Mock the Responses API - this is what we actually use
    fake_response = MagicMock()
    fake_response.output_text = "Test response"
    fake_response.id = "resp_mock_123"
    mock.responses.create = AsyncMock(return_value=fake_response)

    # Mock async close method
    mock.close = AsyncMock()

    # Mock file operations (async)
    mock_file = MagicMock()
    mock_file.id = "file_test123"
    mock.files.create = AsyncMock(return_value=mock_file)

    # Mock vector store operations (async)
    mock_vs = MagicMock()
    mock_vs.id = "vs_test123"
    mock_vs.status = "completed"

    # Mock both paths - some code uses client.vector_stores, some uses client.beta.vector_stores
    mock.vector_stores.create = AsyncMock(return_value=mock_vs)
    mock.beta.vector_stores.create = AsyncMock(return_value=mock_vs)

    mock_batch = MagicMock()
    mock_batch.status = "completed"
    mock_batch.file_counts = MagicMock(completed=3, failed=0, total=3)
    mock.vector_stores.file_batches.upload_and_poll = AsyncMock(return_value=mock_batch)
    mock.beta.vector_stores.file_batches.upload_and_poll = AsyncMock(
        return_value=mock_batch
    )

    mock.vector_stores.delete = AsyncMock()
    mock.beta.vector_stores.delete = AsyncMock()

    return mock


@pytest.fixture
def mock_openai_factory(mock_openai_client):
    """Patch OpenAIClientFactory to return the mock client."""

    # Create an async mock that returns the client
    async def mock_get_instance(*args, **kwargs):
        return mock_openai_client

    with (
        patch(
            "mcp_second_brain.utils.vector_store.OpenAIClientFactory.get_instance",
            new=mock_get_instance,
        ),
        patch(
            "mcp_second_brain.utils.vector_store_files.OpenAIClientFactory.get_instance",
            new=mock_get_instance,
        ),
        patch(
            "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance",
            new=mock_get_instance,
        ),
    ):
        yield mock_openai_client


@pytest.fixture
def mock_vertex_client():
    """Mock Vertex AI client for testing."""
    mock = MagicMock()

    # Mock generate_content response
    mock_response = MagicMock()
    mock_response.text = "Test Gemini response"
    mock.generate_content.return_value = mock_response

    # Mock generate_content_stream for streaming responses
    mock_chunk = MagicMock()
    mock_chunk.text = "Test Gemini response"
    mock.models.generate_content_stream.return_value = [mock_chunk]

    return mock


@pytest.fixture
def sample_tool_params():
    """Common test parameters for tool execution."""
    return {
        "instructions": "Test instruction",
        "output_format": "plain text",
        "context": [],
    }


# Async fixtures
@pytest_asyncio.fixture
async def mock_tool_executor():
    """Mock ToolExecutor for integration tests."""
    from mcp_second_brain.tools.executor import ToolExecutor

    executor = ToolExecutor()
    # We'll patch the adapters in individual tests
    return executor


# Helper functions
def create_file_with_size(path: Path, size_kb: int, content: str = "x") -> Path:
    """Create a file with specific size in KB."""
    path.write_text(content * (size_kb * 1024 // len(content)))
    return path


def assert_no_secrets_in_logs(caplog, secrets: list[str]):
    """Assert that none of the secrets appear in logs."""
    log_text = caplog.text.lower()
    for secret in secrets:
        assert secret.lower() not in log_text, f"Secret '{secret}' found in logs!"


# Helper fixtures for MockAdapter-based testing
@pytest.fixture
def parse_adapter_response():
    """Parse the JSON string returned by MockAdapter."""

    def _parse(resp: str) -> dict:
        import json

        return json.loads(resp)

    return _parse


@pytest.fixture
def mock_adapter_error():
    """Factory for making MockAdapter.generate raise a given exception."""
    from unittest.mock import patch

    def _factory(exc: Exception):
        return patch(
            "mcp_second_brain.adapters.mock_adapter.MockAdapter.generate",
            side_effect=exc if isinstance(exc, Exception) else exc(),
        )

    return _factory


# Keep vector store mocking since it's a separate concern
@pytest.fixture(autouse=True)
def mock_vector_store_client(monkeypatch, mock_openai_client):
    """Mock vector store client to prevent real API calls."""
    # This mock handles vector stores created for ad-hoc 'attachments'.
    import mcp_second_brain.utils.vector_store as vs_utils

    monkeypatch.setattr(vs_utils, "get_client", Mock(return_value=mock_openai_client))

    # This is the most critical patch. It replaces the store_conversation_memory
    # function inside the executor module with a harmless AsyncMock. This prevents
    # the function from running at all, thus avoiding any real API calls for
    # conversation memory.
    monkeypatch.setattr(
        "mcp_second_brain.memory.conversation.store_conversation_memory",
        AsyncMock(return_value=None),
    )

    # (Optional but good practice) You can also mock where the client is created
    # for the memory system itself, though the patch above is sufficient.
    import mcp_second_brain.memory.config as memory_config

    monkeypatch.setattr(
        memory_config, "get_client", Mock(return_value=mock_openai_client)
    )


@pytest_asyncio.fixture
async def run_tool():
    """Convenience helper that executes a tool by name using the real executor."""
    from mcp_second_brain.tools.executor import executor
    from mcp_second_brain.tools.registry import list_tools

    async def _inner(tool_name: str, **kwargs):
        metadata = list_tools()[tool_name]
        return await executor.execute(metadata, **kwargs)

    return _inner


@pytest.fixture
async def mcp_server():
    """Create MCP server instance for testing."""
    # Import here to ensure MCP_ADAPTER_MOCK is set first
    from mcp_second_brain.server import mcp

    # Return the server instance
    return mcp


# Virtual clock fixture for speeding up time-based tests
class VirtualClock:
    """Virtual clock that advances time instantly without actual delays."""

    def __init__(self):
        self.current_time = time.time()
        self.monotonic_time = time.monotonic()
        self.sleep_history = []
        # Store original sleep function to avoid recursion
        self._original_sleep = asyncio.sleep

    def advance_time(self, seconds):
        """Advance virtual time by given seconds."""
        self.current_time += seconds
        self.monotonic_time += seconds

    def time(self):
        """Return current virtual time."""
        return self.current_time

    def monotonic(self):
        """Return current virtual monotonic time."""
        return self.monotonic_time

    async def sleep(self, seconds):
        """Virtual sleep that advances time without actual delay."""
        self.sleep_history.append(seconds)
        self.advance_time(seconds)
        # Yield control using the real sleep with zero delay
        # We need to use the original asyncio.sleep to avoid recursion
        await self._original_sleep(0)

    def get_total_sleep_time(self):
        """Get total time that would have been slept."""
        return sum(self.sleep_history)


@pytest.fixture
def virtual_clock(monkeypatch):
    """Replace time functions with virtual clock for fast tests."""
    # Store original before creating clock
    original_sleep = asyncio.sleep

    clock = VirtualClock()
    clock._original_sleep = original_sleep

    # Patch time functions
    monkeypatch.setattr(time, "time", clock.time)
    monkeypatch.setattr(time, "monotonic", clock.monotonic)
    monkeypatch.setattr(asyncio, "sleep", clock.sleep)

    return clock


@pytest.fixture(scope="session")
def fast_tests_mode():
    """Check if we're running in fast tests mode."""
    # Could be controlled by env var or pytest marker
    return os.getenv("FAST_TESTS", "1") == "1"


@pytest.fixture(autouse=True)
def auto_virtual_clock(request, monkeypatch, fast_tests_mode):
    """Automatically apply virtual clock to unit tests unless disabled."""
    # Only apply to unit tests
    if not hasattr(request.node, "get_closest_marker"):
        return

    unit_marker = request.node.get_closest_marker("unit")
    no_virtual_clock = request.node.get_closest_marker("no_virtual_clock")

    if unit_marker and fast_tests_mode and not no_virtual_clock:
        # Store original before creating clock
        original_sleep = asyncio.sleep

        clock = VirtualClock()
        clock._original_sleep = original_sleep

        monkeypatch.setattr(time, "time", clock.time)
        monkeypatch.setattr(time, "monotonic", clock.monotonic)
        monkeypatch.setattr(asyncio, "sleep", clock.sleep)
        return clock


@contextlib.contextmanager
def mock_clock(monkeypatch, start: int = 1_000_000):
    """
    Freeze time.time(); yield a function that can be called
    to advance the fake clock.
    """
    current = {"t": start}
    monkeypatch.setattr(time, "time", lambda: current["t"])
    yield lambda seconds: current.__setitem__("t", current["t"] + seconds)
