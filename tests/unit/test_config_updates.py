"""Test configuration updates for PR #29."""

import pytest
import os
from unittest.mock import patch
from mcp_second_brain.config import Settings, get_settings


class TestConfigurationUpdates:
    """Test new configuration fields added in PR #29."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_provider_config_defaults(self, tmp_path, monkeypatch):
        """Test that provider configs have proper defaults."""
        # Change to temp directory to avoid loading .env file
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()

        settings = Settings()

        # Vertex defaults
        assert settings.vertex.max_output_tokens is None  # No default, adapter decides
        assert settings.vertex.max_function_calls == 500

        # OpenAI defaults
        assert settings.openai.max_output_tokens is None  # No default, adapter decides
        assert settings.openai.max_function_calls == 500

    def test_thread_pool_config(self, tmp_path, monkeypatch):
        """Test thread pool configuration."""
        # Change to temp directory to avoid loading .env file
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()

        settings = Settings()

        # Default thread pool workers
        assert settings.mcp.thread_pool_workers == 10

    def test_provider_config_env_override(self):
        """Test that environment variables override provider defaults."""
        with patch.dict(
            os.environ,
            {
                "VERTEX__MAX_OUTPUT_TOKENS": "4096",
                "VERTEX__MAX_FUNCTION_CALLS": "100",
                "OPENAI__MAX_OUTPUT_TOKENS": "32768",
                "OPENAI__MAX_FUNCTION_CALLS": "200",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            assert settings.vertex.max_output_tokens == 4096
            assert settings.vertex.max_function_calls == 100
            assert settings.openai.max_output_tokens == 32768
            assert settings.openai.max_function_calls == 200

    def test_thread_pool_env_override(self):
        """Test thread pool configuration from environment."""
        with patch.dict(os.environ, {"MCP__THREAD_POOL_WORKERS": "20"}, clear=True):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            assert settings.mcp.thread_pool_workers == 20

    def test_thread_pool_validation(self):
        """Test thread pool worker count validation."""
        # Valid range: 1-100
        with patch.dict(os.environ, {"MCP__THREAD_POOL_WORKERS": "0"}, clear=True):
            get_settings.cache_clear()
            with pytest.raises(ValueError):
                Settings(_env_file=None)

        with patch.dict(os.environ, {"MCP__THREAD_POOL_WORKERS": "101"}, clear=True):
            get_settings.cache_clear()
            with pytest.raises(ValueError):
                Settings(_env_file=None)

    def test_yaml_config_with_provider_limits(self, tmp_path, monkeypatch):
        """Test YAML configuration with provider limits."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  thread_pool_workers: 15

providers:
  vertex:
    max_output_tokens: 2048
    max_function_calls: 50
  openai:
    max_output_tokens: 16384
    max_function_calls: 100
""")

        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))
        get_settings.cache_clear()

        settings = Settings(_env_file=None)

        # Thread pool from YAML
        assert settings.mcp.thread_pool_workers == 15

        # Provider limits from YAML
        assert settings.vertex.max_output_tokens == 2048
        assert settings.vertex.max_function_calls == 50
        assert settings.openai.max_output_tokens == 16384
        assert settings.openai.max_function_calls == 100
