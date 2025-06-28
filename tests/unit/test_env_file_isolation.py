"""Test configuration loading precedence and isolation."""

import os
from unittest.mock import patch
from mcp_second_brain.config import Settings, get_settings


class TestEnvFileIsolation:
    """Test configuration loading without .env file support."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_dotenv_file_is_ignored(self, tmp_path, monkeypatch):
        """.env files should be ignored by the new config system."""
        # Create a .env file to ensure it's NOT loaded
        env_file = tmp_path / ".env"
        env_file.write_text("""
OPENAI_API_KEY=from-env-file
VERTEX_PROJECT=env-file-project
HOST=env-file-host
PORT=9999
""")

        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        # Clear environment to ensure we're only testing .env loading
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            # Should use defaults, not values from .env file
            assert settings.openai.api_key is None
            assert settings.vertex.project is None
            assert settings.mcp.host == "127.0.0.1"  # default
            assert settings.mcp.port == 8000  # default

    def test_env_vars_are_loaded_correctly(self):
        """Test that environment variables are loaded correctly."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "from-env-var",
                "PORT": "7777",
                "MCP_CONFIG_FILE": "/nonexistent/config.yaml",  # Prevent loading default config
                "MCP_SECRETS_FILE": "/nonexistent/secrets.yaml",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()

            # Environment variables should still be loaded
            assert settings.openai.api_key == "from-env-var"
            assert settings.mcp.port == 7777

    def test_yaml_is_loaded_correctly(self, tmp_path, monkeypatch):
        """Test that YAML config is loaded correctly."""
        # Create YAML config
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: yaml-host
  port: 8888
providers:
  openai:
    api_key: yaml-api-key
""")

        with patch.dict(
            os.environ,
            {
                "MCP_CONFIG_FILE": str(config_yaml),
                "MCP_SECRETS_FILE": "/nonexistent/secrets.yaml",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()

            # YAML should be loaded
            assert settings.mcp.host == "yaml-host"
            assert settings.mcp.port == 8888
            assert settings.openai.api_key == "yaml-api-key"

    def test_yaml_precedence(self, tmp_path, monkeypatch):
        """Test that YAML configuration works correctly."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: from-yaml
  port: 7777
""")

        # YAML values should be loaded
        with patch.dict(
            os.environ,
            {
                "MCP_CONFIG_FILE": str(config_yaml),
                "MCP_SECRETS_FILE": "/nonexistent/secrets.yaml",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()
            assert settings.mcp.host == "from-yaml"
            assert settings.mcp.port == 7777

    def test_defaults_in_clean_environment(self):
        """Test that defaults are used in a clean environment."""
        # Simulate a test that needs clean environment
        with patch.dict(
            os.environ,
            {
                "MCP_CONFIG_FILE": "/nonexistent/config.yaml",
                "MCP_SECRETS_FILE": "/nonexistent/secrets.yaml",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()

            # All values should be defaults or None
            assert settings.openai.api_key is None
            assert settings.vertex.project is None
            assert settings.anthropic.api_key is None
            assert settings.mcp.host == "127.0.0.1"
            assert settings.mcp.port == 8000
            assert settings.mcp.thread_pool_workers == 10

            # Provider defaults are tested separately now
