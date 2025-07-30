"""
Shared test fixtures and configuration for MCP The-Force tests.
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

# Production database names that must be isolated in tests
# WARNING: If you add a new SQLite database to the project, you MUST add it here!
# The test_database_isolation_coverage.py test will fail if you forget.
PRODUCTION_DBS = {
    ".mcp_sessions.sqlite3",
    ".stable_list_cache.sqlite3",
    ".mcp_logs.sqlite3",
    ".mcp_vector_stores.db",
    "session_cache.db",
}

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


@pytest.fixture(autouse=True)
def isolate_test_databases(tmp_path, monkeypatch):
    """Ensure tests use isolated databases, not production ones.

    This fixture intercepts SQLite connections to redirect production database
    paths to temporary test databases. This approach is safe because:
    - No global state is modified
    - Monkeypatch automatically cleans up on test failure
    - Only specific database paths are redirected
    """
    import sqlite3
    import shutil

    # Use the module-level PRODUCTION_DBS set defined at top of file

    # Create test database mapping
    test_db_map = {}
    for db_name in PRODUCTION_DBS:
        test_path = tmp_path / f"test_{db_name}"
        # Ensure parent directory exists
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_db_map[db_name] = str(test_path)

    # Store the original sqlite3.connect
    original_connect = sqlite3.connect

    def mock_connect(database, *args, **kwargs):
        """Redirect production database paths to test paths."""
        # Skip special SQLite databases
        if database == ":memory:" or not isinstance(database, str):
            return original_connect(database, *args, **kwargs)

        # Convert to Path for easier handling
        db_path = Path(database)
        db_name = db_path.name

        # Check if this is a production database (by name)
        if db_name in PRODUCTION_DBS:
            # Redirect to test database
            database = test_db_map[db_name]

        # Also check if the full path ends with production database name
        elif any(database.endswith(prod_db) for prod_db in PRODUCTION_DBS):
            # Extract the production db name and redirect
            for prod_db in PRODUCTION_DBS:
                if database.endswith(prod_db):
                    database = test_db_map[prod_db]
                    break

        # Call original connect with potentially redirected path
        return original_connect(database, *args, **kwargs)

    # Patch sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", mock_connect)

    # Clear any existing singleton instances before test
    from mcp_the_force import unified_session_cache as usc_module

    if hasattr(usc_module, "_instance") and usc_module._instance is not None:
        try:
            usc_module._instance.close()
        except Exception:
            pass  # Ignore errors during cleanup
        usc_module._instance = None

    yield

    # Cleanup after test
    try:
        # Close and clear singleton
        if hasattr(usc_module, "_instance") and usc_module._instance is not None:
            try:
                usc_module._instance.close()
            except Exception:
                pass  # Ignore errors during cleanup
            usc_module._instance = None

        # Also try to close via the public interface
        from mcp_the_force.unified_session_cache import unified_session_cache

        try:
            unified_session_cache.close()
        except Exception:
            pass  # Ignore errors during cleanup

    finally:
        # Remove test databases - tmp_path is automatically cleaned up by pytest
        # but we can be explicit about it
        if tmp_path.exists():
            shutil.rmtree(tmp_path, ignore_errors=True)


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
            from mcp_the_force.adapters import _ADAPTER_CACHE

            _ADAPTER_CACHE.clear()
            # Use print since logger might not be configured yet in test setup
            print("INFO: Cleared adapter cache for integration tests")
        except ImportError:
            pass  # If we can't import, tests will fail for other reasons


@pytest.fixture
def mock_env(monkeypatch):
    """Set up test environment variables."""
    # Clear the cached settings first
    from mcp_the_force.config import get_settings

    get_settings.cache_clear()

    test_env = {
        "OPENAI_API_KEY": "test-openai-key",
        "XAI_API_KEY": "test-xai-key",
        "ANTHROPIC_API_KEY": "test-anthropic-key",
        "VERTEX_PROJECT": "test-project",
        "VERTEX_LOCATION": "us-central1",
        "CONTEXT_PERCENTAGE": "0.85",
        "LOG_LEVEL": "WARNING",  # Reduce noise in tests
        "VICTORIA_LOGS_URL": "",  # Disable VictoriaLogs in tests
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
    # Use a unique ID per test to avoid database conflicts
    import uuid

    mock_vs = MagicMock()
    mock_vs.id = f"vs_test_{uuid.uuid4().hex[:8]}"
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

    # Mock vector store search for SearchHistoryService
    mock_search_response = MagicMock()
    mock_search_response.data = []
    mock.vector_stores.search = MagicMock(return_value=mock_search_response)

    # Mock vector store retrieve for memory config
    # This should return the same store that was created
    def mock_retrieve(store_id):
        mock_retrieved = MagicMock()
        mock_retrieved.id = store_id
        return mock_retrieved

    mock.vector_stores.retrieve = AsyncMock(side_effect=mock_retrieve)

    return mock


@pytest.fixture
def mock_openai_factory(mock_openai_client, tmp_path, monkeypatch):
    """Patch OpenAIClientFactory to return the mock client."""

    # First, ensure we're using test databases for memory config
    test_db_path = tmp_path / "test_memory.db"
    monkeypatch.setenv("SESSION_DB_PATH", str(test_db_path))

    # Clear any cached settings
    from mcp_the_force.config import get_settings

    get_settings.cache_clear()

    # Clear any existing memory config instances
    from mcp_the_force.memory import config as memory_config_module
    from mcp_the_force.memory import async_config as async_config_module

    if hasattr(memory_config_module, "_memory_config"):
        memory_config_module._memory_config = None
    if hasattr(async_config_module, "_async_memory_config"):
        async_config_module._async_memory_config = None

    # Clear SearchHistoryService singletons inside the context to avoid circular import
    try:
        from mcp_the_force.local_services.search_history import SearchHistoryService

        SearchHistoryService._client = None
        SearchHistoryService._memory_config = None
    except ImportError:
        # If there's a circular import, skip clearing
        pass

    # Create an async mock that returns the client
    async def mock_get_instance(*args, **kwargs):
        return mock_openai_client

    with (
        patch(
            "mcp_the_force.vectorstores.openai.openai_vectorstore.AsyncOpenAI",
            return_value=mock_openai_client,
        ),
        patch(
            "mcp_the_force.adapters.openai.client.OpenAIClientFactory.get_instance",
            new=mock_get_instance,
        ),
        patch(
            "mcp_the_force.local_services.search_history.get_async_memory_config",
            return_value=Mock(
                get_active_conversation_store=AsyncMock(return_value="test_store_conv"),
                get_active_commit_store=AsyncMock(return_value="test_store_commit"),
            ),
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
        "priority_context": [],
    }


# Async fixtures
@pytest_asyncio.fixture
async def mock_tool_executor():
    """Mock ToolExecutor for integration tests."""
    from mcp_the_force.tools.executor import ToolExecutor

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

    def _parse(resp) -> dict:
        import json

        # Handle OpenAI models that return dict with 'content' field
        if isinstance(resp, dict) and "content" in resp:
            return json.loads(resp["content"])
        # Handle other models that return JSON string directly
        return json.loads(resp)

    return _parse


@pytest.fixture
def mock_adapter_error():
    """Factory for making MockAdapter.generate raise a given exception."""
    from unittest.mock import patch

    def _factory(exc: Exception):
        return patch(
            "mcp_the_force.adapters.mock_adapter.MockAdapter.generate",
            side_effect=exc if isinstance(exc, Exception) else exc(),
        )

    return _factory


# Configure tests to use inmemory vector store provider
@pytest.fixture(autouse=True)
def use_inmemory_vectorstore(monkeypatch):
    """Ensure all tests use the in-memory vector store provider by default."""
    monkeypatch.setenv("MCP__DEFAULT_VECTOR_STORE_PROVIDER", "inmemory")


# Keep vector store mocking since it's a separate concern
@pytest.fixture(autouse=True)
def mock_vector_store_client(monkeypatch, mock_openai_client):
    """Mock vector store client to prevent real API calls."""
    # This is the most critical patch. It replaces the store_conversation_memory
    # function inside the executor module with a harmless AsyncMock. This prevents
    # the function from running at all, thus avoiding any real API calls for
    # conversation memory.
    monkeypatch.setattr(
        "mcp_the_force.memory.conversation.store_conversation_memory",
        AsyncMock(return_value=None),
    )


@pytest_asyncio.fixture
async def run_tool():
    """Convenience helper that executes a tool by name using the real executor."""
    from mcp_the_force.tools.executor import executor
    from mcp_the_force.tools.registry import list_tools

    async def _inner(tool_name: str, **kwargs):
        metadata = list_tools()[tool_name]
        return await executor.execute(metadata, **kwargs)

    return _inner


@pytest.fixture
async def mcp_server():
    """Create MCP server instance for testing."""
    # Import here to ensure MCP_ADAPTER_MOCK is set first
    from mcp_the_force.server import mcp

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
