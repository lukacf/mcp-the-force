"""Unit tests for OllamaAdapter class."""

import pytest
from unittest.mock import MagicMock, patch

from mcp_the_force.adapters.ollama.adapter import OllamaAdapter
from mcp_the_force.adapters.ollama.params import OllamaToolParams
from mcp_the_force.adapters.ollama.capabilities import OllamaCapabilities
from mcp_the_force.adapters.ollama.overrides import ResolvedCapabilities
from mcp_the_force.adapters.errors import ConfigurationException


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock()
    settings.ollama.enabled = True
    settings.ollama.host = "http://localhost:11434"
    settings.ollama.default_context_window = 16384
    return settings


class TestOllamaAdapterInit:
    """Tests for OllamaAdapter initialization."""

    def test_init_basic(self, mock_settings):
        """Test basic initialization."""
        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            adapter = OllamaAdapter("llama3:latest")

            assert adapter.model_name == "llama3:latest"
            assert adapter.display_name == "Ollama llama3:latest"
            assert isinstance(adapter.capabilities, OllamaCapabilities)
            assert adapter.capabilities.model_name == "llama3:latest"

    def test_init_with_capabilities(self, mock_settings):
        """Test initialization sets default capabilities."""
        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            adapter = OllamaAdapter("mistral:7b")

            assert (
                adapter.capabilities.max_context_window == 16384
            )  # Reasonable default
            assert adapter.capabilities.supports_tools is True
            assert adapter.capabilities.supports_streaming is True
            assert adapter.capabilities.supports_structured_output is True

    def test_init_with_resolved_capabilities(self, mock_settings):
        """Test initialization uses resolved capabilities when available."""
        # Mock resolved capabilities
        resolved_caps = ResolvedCapabilities(
            model_name="llama3:latest",
            max_context_window=131072,
            description="llama3:latest (Llama 8B)",
            source="discovered",
        )

        mock_blueprint_gen = MagicMock()
        mock_blueprint_gen.get_capabilities.return_value = {
            "llama3:latest": resolved_caps
        }

        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "mcp_the_force.adapters.ollama.blueprint_generator", mock_blueprint_gen
            ):
                adapter = OllamaAdapter("llama3:latest")

                assert adapter.model_name == "llama3:latest"
                assert adapter.capabilities.max_context_window == 131072
                assert adapter.capabilities.model_name == "llama3:latest"

    def test_init_with_memory_warning(self, mock_settings):
        """Test initialization logs memory warnings when present."""
        # Mock resolved capabilities with memory warning
        resolved_caps = ResolvedCapabilities(
            model_name="gpt-oss:120b",
            max_context_window=32768,
            description="gpt-oss:120b",
            source="memory-limited",
            memory_warning="Requested context exceeds memory-safe limit. Model uses ~60.0GB.",
        )

        mock_blueprint_gen = MagicMock()
        mock_blueprint_gen.get_capabilities.return_value = {
            "gpt-oss:120b": resolved_caps
        }

        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "mcp_the_force.adapters.ollama.blueprint_generator", mock_blueprint_gen
            ):
                with patch(
                    "mcp_the_force.adapters.ollama.adapter.logger"
                ) as mock_logger:
                    adapter = OllamaAdapter("gpt-oss:120b")

                    assert adapter.capabilities.max_context_window == 32768
                    mock_logger.warning.assert_called_once()
                    assert "Memory warning" in mock_logger.warning.call_args[0][0]

    def test_init_fallback_to_default(self, mock_settings):
        """Test initialization falls back to defaults when no resolved capabilities found."""
        mock_blueprint_gen = MagicMock()
        mock_blueprint_gen.get_capabilities.return_value = {}  # No resolved capabilities

        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "mcp_the_force.adapters.ollama.blueprint_generator", mock_blueprint_gen
            ):
                with patch(
                    "mcp_the_force.adapters.ollama.adapter.logger"
                ) as mock_logger:
                    adapter = OllamaAdapter("unknown:model")

                    assert (
                        adapter.capabilities.max_context_window == 16384
                    )  # Config default
                    mock_logger.warning.assert_called_once()
                    assert (
                        "Could not find resolved capabilities"
                        in mock_logger.warning.call_args[0][0]
                    )


class TestOllamaAdapterValidation:
    """Tests for environment validation."""

    def test_validate_environment_success(self, mock_settings):
        """Test successful environment validation."""
        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            OllamaAdapter("llama3:latest")
            # adapter._validate_environment() is called in __init__, so no need to call again

    def test_validate_environment_disabled(self, mock_settings):
        """Test validation fails when Ollama is disabled."""
        mock_settings.ollama.enabled = False

        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            with pytest.raises(ConfigurationException) as exc_info:
                OllamaAdapter("llama3:latest")

            assert "disabled in configuration" in str(exc_info.value)

    def test_validate_environment_no_host(self, mock_settings):
        """Test validation fails when host is not configured."""
        mock_settings.ollama.host = ""

        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            with pytest.raises(ConfigurationException) as exc_info:
                OllamaAdapter("llama3:latest")

            assert "host not configured" in str(exc_info.value)


class TestOllamaAdapterRequestBuilding:
    """Tests for request parameter building."""

    def test_build_basic_request(self, mock_settings):
        """Test building basic request parameters."""
        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            adapter = OllamaAdapter("llama3:latest")
            adapter.capabilities.max_context_window = 32768

            params = OllamaToolParams()
            params.instructions = "Test prompt"
            params.output_format = "plain text"
            params.context = []
            params.session_id = "test-session"

            conversation = [{"role": "user", "content": "Hello"}]

            request = adapter._build_request_params(conversation, params, [])

        assert request["model"] == "ollama_chat/llama3:latest"
        assert request["input"] == conversation
        assert request["api_base"] == "http://localhost:11434"
        assert request["extra_headers"]["options"]["num_ctx"] == 32768

    def test_build_request_uses_resolved_context_window(self, mock_settings):
        """Test that request uses the resolved context window from capabilities."""
        # Mock resolved capabilities with large context window
        resolved_caps = ResolvedCapabilities(
            model_name="llama3:latest",
            max_context_window=131072,
            description="llama3:latest (Llama 8B)",
            source="discovered",
        )

        mock_blueprint_gen = MagicMock()
        mock_blueprint_gen.get_capabilities.return_value = {
            "llama3:latest": resolved_caps
        }

        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "mcp_the_force.adapters.ollama.blueprint_generator", mock_blueprint_gen
            ):
                adapter = OllamaAdapter("llama3:latest")

                params = OllamaToolParams()
                params.instructions = "Test"
                params.output_format = "text"
                params.context = []
                params.session_id = "test"

                request = adapter._build_request_params([], params, [])

                # Verify the resolved context window is actually used in the request
                assert request["extra_headers"]["options"]["num_ctx"] == 131072

    def test_build_request_with_parameters(self, mock_settings):
        """Test building request with various parameters."""
        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            adapter = OllamaAdapter("mistral:7b")

            params = OllamaToolParams()
            params.instructions = "Test"
            params.output_format = "text"
            params.context = []
            params.session_id = "test"
            params.temperature = 0.5
            params.max_tokens = 2048
            params.keep_alive = "10m"
            params.seed = 42
            params.top_p = 0.9
            params.top_k = 40
            params.repeat_penalty = 1.1

            request = adapter._build_request_params([], params, [])

        options = request["extra_headers"]["options"]
        assert options["temperature"] == 0.5
        assert options["num_predict"] == 2048
        assert options["keep_alive"] == "10m"
        assert options["seed"] == 42
        assert options["top_p"] == 0.9
        assert options["top_k"] == 40
        assert options["repeat_penalty"] == 1.1

    def test_build_request_with_json_format(self, mock_settings):
        """Test building request with JSON format."""
        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            adapter = OllamaAdapter("llama3:latest")

            params = OllamaToolParams()
            params.instructions = "Test"
            params.output_format = "json"
            params.context = []
            params.session_id = "test"
            params.format = "json"

            request = adapter._build_request_params([], params, [])

        assert request["response_format"] == {"type": "json_object"}

    # Note: structured_output_schema test removed because Ollama models don't support it

    def test_build_request_with_tools(self, mock_settings):
        """Test building request with tool support."""
        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            adapter = OllamaAdapter("llama3:latest")

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather info",
                        "parameters": {
                            "type": "object",
                            "properties": {"location": {"type": "string"}},
                        },
                    },
                }
            ]

            params = OllamaToolParams()
            params.instructions = "Test"
            params.output_format = "text"
            params.context = []
            params.session_id = "test"

            request = adapter._build_request_params(
                [], params, tools, tool_choice="auto"
            )

        assert request["tools"] == tools
        assert request["tool_choice"] == "auto"

    def test_model_prefix(self, mock_settings):
        """Test the model prefix for LiteLLM."""
        with patch(
            "mcp_the_force.adapters.ollama.adapter.get_settings",
            return_value=mock_settings,
        ):
            adapter = OllamaAdapter("any:model")
            assert adapter._get_model_prefix() == "ollama_chat"
