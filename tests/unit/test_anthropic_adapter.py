"""Tests for Anthropic adapter."""

from unittest.mock import patch
import pytest

from mcp_the_force.adapters.anthropic.adapter import AnthropicAdapter
from mcp_the_force.adapters.anthropic.capabilities import (
    Claude4OpusCapabilities,
    Claude4SonnetCapabilities,
    Claude3OpusCapabilities,
)
from mcp_the_force.adapters.anthropic.params import AnthropicToolParams


class TestAnthropicAdapter:
    """Test Anthropic adapter functionality."""

    def test_supported_models(self):
        """Test that all expected models are supported."""
        models = AnthropicAdapter.get_supported_models()
        assert "claude-opus-4-20250514" in models
        assert "claude-sonnet-4-20250514" in models
        assert "claude-3-opus-20240229" in models
        assert len(models) == 3

    def test_model_string_format(self):
        """Test model string formatting for LiteLLM."""
        adapter = AnthropicAdapter()
        assert adapter._get_model_prefix() == "anthropic"
        assert adapter.model_name == "claude-opus-4-20250514"  # Default model

    @patch("mcp_the_force.config.get_settings")
    def test_api_key_validation(self, mock_settings):
        """Test API key validation during initialization."""
        # Test with valid API key
        mock_settings.return_value.anthropic.api_key = "sk-ant-test-key"
        adapter = AnthropicAdapter()  # Should not raise
        assert adapter.model_name == "claude-opus-4-20250514"

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
        assert params.get_thinking_budget() == 8192

        # Test low effort
        params.reasoning_effort = "low"
        assert params.get_thinking_budget() == 4096

        # Test high effort
        params.reasoning_effort = "high"
        assert params.get_thinking_budget() == 16384

        # Explicit budget overrides effort
        params.thinking_budget = 32768
        assert params.get_thinking_budget() == 32768

    def test_claude4_opus_capabilities(self):
        """Test Claude 4 Opus capabilities."""
        caps = Claude4OpusCapabilities()
        assert caps.model_name == "claude-opus-4-20250514"
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
        assert caps.max_context_window == 200_000
        assert caps.max_output_tokens == 64_000
        assert caps.supports_reasoning_effort is True

    def test_claude3_opus_capabilities(self):
        """Test Claude 3 Opus capabilities."""
        caps = Claude3OpusCapabilities()
        assert caps.model_name == "claude-3-opus-20240229"
        assert caps.max_context_window == 200_000
        assert caps.max_output_tokens == 8_000
        assert caps.supports_reasoning_effort is False  # No extended thinking
