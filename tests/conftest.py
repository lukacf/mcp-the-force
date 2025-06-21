"""
Shared test fixtures and configuration for MCP Second-Brain tests.
"""
import sys
import os
from pathlib import Path
import pytest
from unittest.mock import MagicMock, Mock, AsyncMock

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
    # Only check if we're in internal or MCP integration tests
    if any(arg for arg in sys.argv if 'tests/internal' in arg or 'tests/integration_mcp' in arg):
        if os.getenv("MCP_ADAPTER_MOCK") != "1":
            pytest.fail(
                "MCP_ADAPTER_MOCK=1 must be set before running integration tests.\n"
                "Run: MCP_ADAPTER_MOCK=1 pytest tests/internal"
            )
        
        # Verify the adapter was actually injected
        try:
            from mcp_second_brain.adapters import ADAPTER_REGISTRY
            from mcp_second_brain.adapters.mock_adapter import MockAdapter
            
            for name, adapter_class in ADAPTER_REGISTRY.items():
                if adapter_class is not MockAdapter:
                    pytest.fail(
                        f"Adapter '{name}' is not using MockAdapter! "
                        f"Got {adapter_class} instead. "
                        "This suggests MCP_ADAPTER_MOCK was set too late."
                    )
        except ImportError:
            # If we can't import, tests will fail anyway
            pass


@pytest.fixture
def mock_env(monkeypatch):
    """Set up test environment variables."""
    # Clear the cached settings first
    from mcp_second_brain.config import get_settings
    get_settings.cache_clear()
    
    test_env = {
        "OPENAI_API_KEY": "test-openai-key",
        "VERTEX_PROJECT": "test-project",
        "VERTEX_LOCATION": "us-central1",
        "MAX_INLINE_TOKENS": "12000",
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
    
    # Mock vector store operations (sync, not async)
    mock_vs = MagicMock()
    mock_vs.id = "vs_test123"
    mock_vs.status = "completed"
    
    # Mock both paths - some code uses client.vector_stores, some uses client.beta.vector_stores
    mock.vector_stores.create = MagicMock(return_value=mock_vs)
    mock.beta.vector_stores.create = MagicMock(return_value=mock_vs)
    
    mock_batch = MagicMock()
    mock_batch.status = "completed"
    mock.vector_stores.file_batches.upload_and_poll = MagicMock(return_value=mock_batch)
    mock.beta.vector_stores.file_batches.upload_and_poll = MagicMock(return_value=mock_batch)
    
    mock.vector_stores.delete = MagicMock()
    mock.beta.vector_stores.delete = MagicMock()
    
    return mock


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
        "context": []
    }


# Async fixtures
@pytest.fixture
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
            side_effect=exc if isinstance(exc, Exception) else exc()
        )
    return _factory


# Keep vector store mocking since it's a separate concern
@pytest.fixture(autouse=True)
def mock_vector_store_client(monkeypatch, mock_openai_client):
    """Mock vector store client to prevent real API calls."""
    import mcp_second_brain.utils.vector_store as vs
    monkeypatch.setattr(vs, "get_client", Mock(return_value=mock_openai_client))


@pytest.fixture
async def run_tool():
    """Convenience helper that executes a tool by name using the real executor."""
    from mcp_second_brain.tools.executor import executor
    from mcp_second_brain.tools.registry import list_tools

    async def _inner(tool_name: str, **kwargs):
        metadata = list_tools()[tool_name]
        return await executor.execute(metadata, **kwargs)
    return _inner