"""
Unit tests for configuration and settings.
"""

import os
import pytest
from unittest.mock import patch
from mcp_second_brain.config import Settings, _deep_merge, get_settings


class TestSettings:
    """Test Settings configuration."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_default_settings(self):
        """Test that default settings are loaded."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            # Check defaults
            assert settings.host == "127.0.0.1"
            assert settings.port == 8000
            assert settings.context_percentage == 0.85  # 85% by default
            assert settings.default_temperature == 1.0

    def test_env_var_override(self, mock_env):
        """Test that environment variables override defaults."""
        # mock_env fixture sets test values
        settings = Settings()

        assert settings.openai_api_key == "test-openai-key"
        assert settings.vertex_project == "test-project"
        assert settings.vertex_location == "us-central1"
        assert (
            settings.context_percentage == 0.85
        )  # Default, not overridden by mock_env

    def test_custom_env_values(self):
        """Test custom environment values."""
        custom_env = {
            "HOST": "0.0.0.0",
            "PORT": "9000",
            "CONTEXT_PERCENTAGE": "0.85",
            "DEFAULT_TEMPERATURE": "0.7",
        }

        with patch.dict(os.environ, custom_env, clear=True):
            settings = Settings()

            assert settings.host == "0.0.0.0"
            assert settings.port == 9000
            assert settings.context_percentage == 0.85
            assert settings.default_temperature == 0.7

    def test_invalid_port(self):
        """Test that invalid port raises error."""
        with patch.dict(os.environ, {"PORT": "not-a-number"}, clear=True):
            with pytest.raises(ValueError):
                Settings()

    def test_temperature_validation(self):
        """Test temperature validation (0.0 to 2.0)."""
        # Valid temperature
        with patch.dict(os.environ, {"DEFAULT_TEMPERATURE": "1.5"}, clear=True):
            settings = Settings()
            assert settings.default_temperature == 1.5

        # Invalid temperature (too high)
        with patch.dict(os.environ, {"DEFAULT_TEMPERATURE": "2.5"}, clear=True):
            get_settings.cache_clear()
            with pytest.raises(ValueError):
                Settings()

    def test_missing_api_keys_allowed(self, tmp_path, monkeypatch):
        """Test that missing API keys don't prevent initialization."""
        # Change to a temp directory with no .env file
        monkeypatch.chdir(tmp_path)

        with patch.dict(os.environ, {}, clear=True):
            get_settings.cache_clear()
            settings = Settings()

            # Should be None when not set
            assert settings.openai_api_key is None
            assert settings.vertex_project is None

    def test_dotenv_loading(self, tmp_path, monkeypatch):
        """Test that .env files are ignored."""
        # Create a .env file
        env_file = tmp_path / ".env"
        env_file.write_text("""
OPENAI_API_KEY=from-dotenv
HOST=192.168.1.1
PORT=3000
""")

        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        # Clear environment first so only the .env file could provide values
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            # .env file should be ignored - defaults remain
            assert settings.openai_api_key is None
            assert settings.host == "127.0.0.1"
            assert settings.port == 8000

    def test_env_precedence_over_dotenv(self, tmp_path, monkeypatch):
        """Test that environment variables take precedence over .env file."""
        # Create a .env file
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=from-dotenv")

        monkeypatch.chdir(tmp_path)

        # Set environment variable
        with patch.dict(os.environ, {"OPENAI_API_KEY": "from-env"}, clear=True):
            settings = Settings()

            # Environment should win
            assert settings.openai_api_key == "from-env"

    def test_case_insensitivity(self):
        """Test that pydantic-settings is case-insensitive by default."""
        with patch.dict(os.environ, {"openai_api_key": "lowercase"}, clear=True):
            settings = Settings()

            # pydantic-settings is case-insensitive, so it should pick up the value
            assert settings.openai_api_key == "lowercase"

    def test_vertex_endpoint_property(self):
        """Test that vertex_endpoint property is computed correctly."""
        with patch.dict(
            os.environ,
            {"VERTEX_PROJECT": "my-project", "VERTEX_LOCATION": "europe-west1"},
            clear=True,
        ):
            settings = Settings()

            assert (
                settings.vertex_endpoint == "projects/my-project/locations/europe-west1"
            )

    def test_get_settings_cached(self):
        """Test that get_settings() returns cached instance."""
        from mcp_second_brain.config import get_settings

        # Clear cache first
        get_settings.cache_clear()

        # Get settings twice
        settings1 = get_settings()
        settings2 = get_settings()

        # Should be the same instance
        assert settings1 is settings2

    def test_backward_compatibility_properties(self):
        """Test backward compatibility properties."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "VERTEX_PROJECT": "test-proj",
                "VERTEX_LOCATION": "test-loc",
                "SESSION_TTL_SECONDS": "7200",
                "MEMORY_ENABLED": "false",
                "MEMORY_ROLLOVER_LIMIT": "5000",
            },
            clear=True,
        ):
            settings = Settings()

            # Test all backward compatibility properties
            assert settings.openai_api_key == "test-key"
            assert settings.vertex_project == "test-proj"
            assert settings.vertex_location == "test-loc"
            assert settings.context_percentage == 0.85
            assert settings.default_temperature == 1.0
            assert settings.session_ttl_seconds == 7200
            assert settings.session_db_path == ".mcp_sessions.sqlite3"
            assert settings.session_cleanup_probability == 0.01
            assert settings.memory_enabled is False
            assert settings.memory_rollover_limit == 5000
            assert settings.memory_session_cutoff_hours == 2
            assert settings.memory_summary_char_limit == 200000
            assert settings.memory_max_files_per_commit == 50

    def test_vertex_oauth_configuration(self):
        """Test Vertex AI OAuth configuration for CI/CD environments."""
        with patch.dict(
            os.environ,
            {
                "GCLOUD_OAUTH_CLIENT_ID": "test-client-id",
                "GCLOUD_OAUTH_CLIENT_SECRET": "test-client-secret",
                "GCLOUD_USER_REFRESH_TOKEN": "test-refresh-token",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()
            assert settings.vertex.oauth_client_id == "test-client-id"
            assert settings.vertex.oauth_client_secret == "test-client-secret"
            assert settings.vertex.user_refresh_token == "test-refresh-token"

            # Also verify they're exported correctly
            env_vars = settings.export_env()
            assert env_vars["GCLOUD_OAUTH_CLIENT_ID"] == "test-client-id"
            assert env_vars["GCLOUD_OAUTH_CLIENT_SECRET"] == "test-client-secret"
            assert env_vars["GCLOUD_USER_REFRESH_TOKEN"] == "test-refresh-token"


class TestYAMLConfiguration:
    """Test YAML-based configuration loading."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_yaml_config_loading(self, tmp_path, monkeypatch):
        """Test loading configuration from YAML files."""
        # Create config.yaml
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: 0.0.0.0
  port: 9000
  context_percentage: 0.9
  default_temperature: 0.3

providers:
  openai:
    enabled: true
  vertex:
    enabled: true
    project: yaml-project
    location: yaml-location

logging:
  level: DEBUG

session:
  ttl_seconds: 7200
  db_path: custom_sessions.db
  
memory:
  enabled: false
  rollover_limit: 5000
""")

        # Create secrets.yaml
        secrets_yaml = tmp_path / "secrets.yaml"
        secrets_yaml.write_text("""
providers:
  openai:
    api_key: yaml-openai-key
  anthropic:
    api_key: yaml-anthropic-key
""")

        # Set config file paths
        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))
        monkeypatch.setenv("MCP_SECRETS_FILE", str(secrets_yaml))

        # Clear any existing API keys from environment to test YAML loading
        for key in [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "VERTEX_PROJECT",
            "VERTEX_LOCATION",
        ]:
            monkeypatch.delenv(key, raising=False)

        # Clear cache and create settings
        get_settings.cache_clear()
        settings = Settings()

        # Test values from config.yaml
        assert settings.mcp.host == "0.0.0.0"
        assert settings.mcp.port == 9000
        assert settings.mcp.context_percentage == 0.9
        assert settings.mcp.default_temperature == 0.3
        assert settings.logging.level == "DEBUG"
        assert settings.session.ttl_seconds == 7200
        assert settings.memory.enabled is False
        assert settings.memory.rollover_limit == 5000

        # Test values from secrets.yaml
        assert settings.openai.api_key == "yaml-openai-key"
        assert settings.anthropic.api_key == "yaml-anthropic-key"

        # Test merged vertex config
        assert settings.vertex.project == "yaml-project"
        assert settings.vertex.location == "yaml-location"

    def test_yaml_env_precedence(self, tmp_path, monkeypatch):
        """Test that environment variables override YAML configuration."""
        # Create config.yaml
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: yaml-host
  port: 8000

providers:
  openai:
    api_key: yaml-key
""")

        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        # Set env vars that should override YAML
        with patch.dict(
            os.environ,
            {
                "HOST": "env-host",
                "PORT": "9000",
                "OPENAI_API_KEY": "env-key",
            },
            clear=False,
        ):
            get_settings.cache_clear()
            settings = Settings()

            # Env vars should win
            assert settings.mcp.host == "env-host"
            assert settings.mcp.port == 9000
            assert settings.openai.api_key == "env-key"

    def test_yaml_legacy_env_precedence(self, tmp_path, monkeypatch):
        """Test configuration precedence: env > YAML > .env > defaults."""
        # Create .env file
        env_file = tmp_path / ".env"
        env_file.write_text("""
HOST=dotenv-host
PORT=7000
OPENAI_API_KEY=dotenv-key
""")

        # Create config.yaml
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: yaml-host
  port: 8000

providers:
  openai:
    api_key: yaml-key
""")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        # Clear any existing API keys from environment to test YAML loading
        for key in ["OPENAI_API_KEY", "HOST", "PORT"]:
            monkeypatch.delenv(key, raising=False)

        # Test with only YAML and .env (YAML should win)
        with patch.dict(os.environ, {}, clear=False):
            settings = Settings()
            assert settings.mcp.host == "yaml-host"
            assert settings.mcp.port == 8000
            assert settings.openai.api_key == "yaml-key"

        # Test with env var override (env should win)
        with patch.dict(os.environ, {"HOST": "env-host"}, clear=False):
            get_settings.cache_clear()
            settings = Settings()
            assert settings.mcp.host == "env-host"  # env wins
            assert settings.mcp.port == 8000  # yaml wins over .env
            assert settings.openai.api_key == "yaml-key"  # yaml wins

    def test_missing_yaml_files(self, monkeypatch):
        """Test that missing YAML files don't break initialization."""
        # Point to non-existent files
        monkeypatch.setenv("MCP_CONFIG_FILE", "/non/existent/config.yaml")
        monkeypatch.setenv("MCP_SECRETS_FILE", "/non/existent/secrets.yaml")

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings()

            # Should fall back to env vars and defaults
            assert settings.openai.api_key == "test-key"
            assert settings.mcp.host == "127.0.0.1"
            assert settings.mcp.port == 8000

    def test_invalid_yaml_syntax(self, tmp_path, monkeypatch):
        """Test handling of invalid YAML syntax."""
        # Create invalid YAML
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: [invalid
  port: 8000
""")

        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        # Should handle gracefully and use defaults
        settings = Settings()
        assert settings.mcp.host == "127.0.0.1"
        assert settings.mcp.port == 8000

    def test_nested_env_vars(self):
        """Test nested environment variables with double underscore."""
        with patch.dict(
            os.environ,
            {
                "OPENAI__API_KEY": "nested-key",
                "VERTEX__PROJECT": "nested-project",
                "MCP__PORT": "9999",
            },
            clear=True,
        ):
            settings = Settings()

            assert settings.openai.api_key == "nested-key"
            assert settings.vertex.project == "nested-project"
            assert settings.mcp.port == 9999

    def test_deep_merge_function(self):
        """Test the _deep_merge utility function."""
        a = {
            "mcp": {"host": "a-host", "port": 8000},
            "providers": {"openai": {"api_key": "a-key"}},
            "list": [1, 2, 3],
        }

        b = {
            "mcp": {"port": 9000, "new_field": "value"},
            "providers": {
                "openai": {"api_key": "b-key"},
                "vertex": {"project": "b-proj"},
            },
            "list": [4, 5],
        }

        result = _deep_merge(a, b)

        # b values should override a values
        assert result["mcp"]["host"] == "a-host"  # kept from a
        assert result["mcp"]["port"] == 9000  # overridden by b
        assert result["mcp"]["new_field"] == "value"  # added from b
        assert result["providers"]["openai"]["api_key"] == "b-key"  # overridden
        assert result["providers"]["vertex"]["project"] == "b-proj"  # added
        assert result["list"] == [4, 5]  # lists are replaced, not merged


class TestConfigurationExport:
    """Test configuration export functionality."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_export_env(self, tmp_path, monkeypatch):
        """Test exporting configuration as environment variables."""
        # Change to temp directory to avoid loading .env file
        monkeypatch.chdir(tmp_path)

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "VERTEX_PROJECT": "test-project",
                "PORT": "9000",
                "MEMORY_ENABLED": "true",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()
            env_vars = settings.export_env()

            assert env_vars["OPENAI_API_KEY"] == "test-key"
            assert env_vars["VERTEX_PROJECT"] == "test-project"
            assert env_vars["PORT"] == "9000"
            assert env_vars["MEMORY_ENABLED"] == "true"
            assert env_vars["HOST"] == "127.0.0.1"  # default

            # Empty values should be filtered out
            assert "ANTHROPIC_API_KEY" not in env_vars

    def test_export_mcp_config(self, tmp_path, monkeypatch):
        """Test exporting configuration as mcp-config.json."""
        # Change to temp directory to avoid loading .env file
        monkeypatch.chdir(tmp_path)

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "VERTEX_PROJECT": "test-project",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()
            mcp_config = settings.export_mcp_config()

            assert "mcpServers" in mcp_config
            assert "second-brain" in mcp_config["mcpServers"]

            server_config = mcp_config["mcpServers"]["second-brain"]
            assert server_config["command"] == "uv"
            assert server_config["args"] == ["run", "--", "mcp-second-brain"]
            assert server_config["timeout"] == 3600000
            assert server_config["env"]["OPENAI_API_KEY"] == "test-key"
            assert server_config["env"]["VERTEX_PROJECT"] == "test-project"


class TestConfigurationValidation:
    """Test configuration validation."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_port_validation(self):
        """Test port number validation."""
        # Valid ports
        for port in [1, 80, 8080, 65535]:
            with patch.dict(os.environ, {"PORT": str(port)}, clear=True):
                settings = Settings()
                assert settings.mcp.port == port

        # Invalid ports
        for port in ["0", "65536", "999999"]:
            with patch.dict(os.environ, {"PORT": port}, clear=True):
                with pytest.raises(ValueError):
                    Settings()

    def test_percentage_validation(self):
        """Test context percentage validation."""
        # Valid percentages
        for pct in ["0.1", "0.5", "0.85", "0.95"]:
            with patch.dict(os.environ, {"CONTEXT_PERCENTAGE": pct}, clear=True):
                settings = Settings()
                assert settings.mcp.context_percentage == float(pct)

        # Invalid percentages
        for pct in ["0.05", "0.99", "1.5"]:
            with patch.dict(os.environ, {"CONTEXT_PERCENTAGE": pct}, clear=True):
                with pytest.raises(ValueError):
                    Settings()

    def test_logging_level_validation(self, tmp_path, monkeypatch):
        """Test logging level validation."""
        # Valid levels
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "debug", "Info"]:
            config_yaml = tmp_path / f"config_{level}.yaml"
            config_yaml.write_text(f"""
logging:
  level: {level}
""")
            monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

            settings = Settings()
            assert settings.logging.level == level.upper()

            get_settings.cache_clear()

        # Invalid level
        config_yaml = tmp_path / "config_invalid.yaml"
        config_yaml.write_text("""
logging:
  level: INVALID
""")
        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        with pytest.raises(ValueError):
            Settings()

    def test_required_fields_with_defaults(self):
        """Test that all required fields have sensible defaults."""
        # Minimal environment
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            # All these should have defaults
            assert settings.mcp.host == "127.0.0.1"
            assert settings.mcp.port == 8000
            assert settings.mcp.context_percentage == 0.85
            assert settings.mcp.default_temperature == 1.0
            assert settings.logging.level == "INFO"
            assert settings.session.ttl_seconds == 3600
            assert settings.memory.enabled is True
            assert settings.memory.rollover_limit == 9500
