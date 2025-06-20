"""
Shared test fixtures and configuration for MCP Second-Brain tests.
"""
import os
import sys
from pathlib import Path
from typing import Dict, Any
import pytest
from unittest.mock import MagicMock, Mock

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_env(monkeypatch):
    """Set up test environment variables."""
    test_env = {
        "OPENAI_API_KEY": "test-openai-key",
        "VERTEX_PROJECT": "test-project",
        "VERTEX_LOCATION": "us-central1",
        "MAX_INLINE_TOKENS": "12000",
        "LOG_LEVEL": "WARNING",  # Reduce noise in tests
    }
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)
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
    """Mock OpenAI client for testing."""
    mock = MagicMock()
    
    # Mock the Responses API structure
    mock.beta.chat.completions.parse.return_value = MagicMock(
        choices=[MagicMock(
            message=MagicMock(
                parsed=MagicMock(response="Test response"),
                refusal=None
            )
        )]
    )
    
    # Mock vector store operations
    mock.beta.vector_stores.create.return_value = MagicMock(
        id="vs_test123",
        status="completed"
    )
    
    return mock


@pytest.fixture
def mock_vertex_client():
    """Mock Vertex AI client for testing."""
    mock = MagicMock()
    
    # Mock generate_content response
    mock_response = MagicMock()
    mock_response.text = "Test Gemini response"
    mock.generate_content.return_value = mock_response
    
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


# Auto-use fixtures to prevent real API calls
@pytest.fixture(autouse=True)
def mock_external_sdks(monkeypatch, mock_openai_client, mock_vertex_client):
    """Automatically mock external SDKs to prevent real API calls."""
    # Mock OpenAI
    mock_openai_module = Mock()
    mock_openai_module.OpenAI = Mock(return_value=mock_openai_client)
    monkeypatch.setitem(sys.modules, "openai", mock_openai_module)
    
    # Mock Google Vertex AI / genai
    mock_genai_module = Mock()
    mock_genai_module.Client = Mock(return_value=mock_vertex_client)
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai_module)
    
    # Also mock the aiplatform module if needed
    mock_aiplatform = Mock()
    monkeypatch.setitem(sys.modules, "google.cloud.aiplatform", mock_aiplatform)