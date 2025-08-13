"""Tests for Anthropic adapter."""

from unittest.mock import patch
import pytest

from mcp_the_force.adapters.anthropic.adapter import AnthropicAdapter
from mcp_the_force.adapters.anthropic.capabilities import (
    Claude41OpusCapabilities,
    Claude4SonnetCapabilities,
    Claude3OpusCapabilities,
)
from mcp_the_force.adapters.anthropic.params import AnthropicToolParams


class TestAnthropicAdapter:
    """Test Anthropic adapter functionality."""

    def test_supported_models(self):
        """Test that all expected models are supported."""
        models = AnthropicAdapter.get_supported_models()
        assert "claude-opus-4-1-20250805" in models
        assert "claude-sonnet-4-20250514" in models
        assert "claude-3-opus-20240229" in models
        assert len(models) == 3

    def test_model_string_format(self):
        """Test model string formatting for LiteLLM."""
        adapter = AnthropicAdapter()
        assert adapter._get_model_prefix() == "anthropic"
        assert adapter.model_name == "claude-opus-4-1-20250805"  # Default model

    @patch("mcp_the_force.config.get_settings")
    def test_api_key_validation(self, mock_settings):
        """Test API key validation during initialization."""
        # Test with valid API key
        mock_settings.return_value.anthropic.api_key = "sk-ant-test-key"
        adapter = AnthropicAdapter()  # Should not raise
        assert adapter.model_name == "claude-opus-4-1-20250805"

        # Test without API key
        mock_settings.return_value.anthropic.api_key = None
        with pytest.raises(ValueError, match="Anthropic API key not configured"):
            AnthropicAdapter()

    def test_thinking_budget_mapping(self):
        """Test thinking budget mapping from reasoning effort."""
        # Create params instance
        params = AnthropicToolParams()

        # Test default
        assert params.reasoning_effort == "medium"
        assert params.get_thinking_budget() == 16384

        # Test low effort
        params.reasoning_effort = "low"
        assert params.get_thinking_budget() == 4096

        # Test high effort
        params.reasoning_effort = "high"
        assert params.get_thinking_budget() == 32768

        # Explicit budget overrides effort
        params.thinking_budget = 32768
        assert params.get_thinking_budget() == 32768

    def test_claude41_opus_capabilities(self):
        """Test Claude 4.1 Opus capabilities."""
        caps = Claude41OpusCapabilities()
        assert caps.model_name == "claude-opus-4-1-20250805"
        assert caps.max_context_window == 200_000
        assert caps.max_output_tokens == 32_000
        assert caps.supports_reasoning_effort is True
        assert caps.supports_vision is True
        assert caps.supports_tools is True
        assert caps.parallel_function_calls is None

    def test_claude4_sonnet_capabilities(self):
        """Test Claude 4 Sonnet capabilities."""
        caps = Claude4SonnetCapabilities()
        assert caps.model_name == "claude-sonnet-4-20250514"
        assert caps.max_context_window == 1_000_000
        assert caps.max_output_tokens == 64_000
        assert caps.supports_reasoning_effort is True

    def test_claude3_opus_capabilities(self):
        """Test Claude 3 Opus capabilities."""
        caps = Claude3OpusCapabilities()
        assert caps.model_name == "claude-3-opus-20240229"
        assert caps.max_context_window == 200_000
        assert caps.max_output_tokens == 8_000
        assert caps.supports_reasoning_effort is False  # No extended thinking

    def test_sonnet_1m_context_header(self):
        """Test that Sonnet 4 includes 1M context beta header."""
        from unittest.mock import Mock

        adapter = AnthropicAdapter("claude-sonnet-4-20250514")

        # Mock params without thinking budget
        params = Mock()
        params.temperature = 0.7
        params.max_tokens = 4096
        params.structured_output_schema = None

        request_params = adapter._build_request_params(
            conversation_input=[{"role": "user", "content": "test"}],
            params=params,
            tools=[],
        )

        # Should include the 1M context beta header
        assert "extra_headers" in request_params
        assert "anthropic-beta" in request_params["extra_headers"]
        assert (
            "context-1m-2025-08-07" in request_params["extra_headers"]["anthropic-beta"]
        )

    def test_sonnet_1m_context_header_with_thinking(self):
        """Test that Sonnet 4 combines 1M context and thinking beta headers."""
        from unittest.mock import Mock

        adapter = AnthropicAdapter("claude-sonnet-4-20250514")

        # Mock params with thinking budget
        params = Mock()
        params.temperature = 0.7
        params.max_tokens = 4096
        params.structured_output_schema = None
        params.get_thinking_budget = Mock(return_value=5000)

        request_params = adapter._build_request_params(
            conversation_input=[{"role": "user", "content": "test"}],
            params=params,
            tools=[],
        )

        # Should include both beta headers
        assert "extra_headers" in request_params
        assert "anthropic-beta" in request_params["extra_headers"]
        beta_header = request_params["extra_headers"]["anthropic-beta"]
        assert "interleaved-thinking-2025-05-14" in beta_header
        assert "context-1m-2025-08-07" in beta_header
