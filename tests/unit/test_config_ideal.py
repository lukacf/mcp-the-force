"""
ASPIRATIONAL TEST FILE - TDD FOR IDEAL CONFIGURATION SYSTEM
===========================================================

WARNING: This test file represents the DESIRED state of the configuration system,
not the current implementation. These tests will FAIL until the configuration
system is refactored to match this specification.

DO NOT modify these tests to make them pass with the current implementation.
Instead, fix the implementation to satisfy these tests.

The ideal configuration system should:
1. Support 4-level hierarchy: MCP JSON > env vars > YAML > defaults
2. Have NO direct env var access bypasses
3. Support all configuration options through all paths
4. Be fully testable and mockable
"""

import json
import os
import pytest
from unittest.mock import patch
from mcp_the_force.config import Settings, get_settings


class TestIdealConfigurationHierarchy:
    """Test the ideal 4-level configuration hierarchy."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_mcp_json_highest_priority(self, tmp_path, monkeypatch):
        """MCP JSON should override everything else."""
        # Create YAML config
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  port: 8000
providers:
  openai:
    api_key: yaml-key
""")

        # Set environment variables
        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")

        # Set MCP JSON config (highest priority)
        mcp_json = {
            "mcpServers": {
                "the-force": {"env": {"PORT": "7000", "OPENAI_API_KEY": "mcp-json-key"}}
            }
        }
        monkeypatch.setenv("MCP_CONFIG_JSON", json.dumps(mcp_json))

        settings = Settings()

        # MCP JSON should win
        assert settings.mcp.port == 7000
        assert settings.openai.api_key == "mcp-json-key"

    def test_complete_hierarchy_precedence(self, tmp_path, monkeypatch):
        """Test full hierarchy: MCP JSON > env > YAML > defaults."""
        # 1. Defaults (lowest priority)
        # port default is 8000

        # 2. YAML config
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  port: 8001
  host: yaml-host
  context_percentage: 0.8
""")
        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        # 3. Environment variables
        monkeypatch.setenv("PORT", "8002")
        monkeypatch.setenv("HOST", "env-host")

        # 4. MCP JSON (only sets port)
        mcp_json = {"mcpServers": {"the-force": {"env": {"PORT": "8003"}}}}
        monkeypatch.setenv("MCP_CONFIG_JSON", json.dumps(mcp_json))

        settings = Settings()

        # Results should follow hierarchy
        assert settings.mcp.port == 8003  # MCP JSON wins
        assert settings.mcp.host == "env-host"  # env wins (no MCP JSON)
        assert settings.mcp.context_percentage == 0.8  # YAML wins (no env/MCP)
        assert settings.mcp.default_temperature == 1.0  # default (nothing set)


class TestNoEnvironmentBypassesAllowed:
    """Test that NO components bypass the configuration system."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_google_adapter_uses_settings(self):
        """Google adapter should use settings, not os.getenv()."""
        with patch.dict(os.environ, {"VERTEX_PROJECT": "env-project"}, clear=True):
            settings = Settings()

            # This represents the ideal: adapter gets config from settings
            assert settings.vertex.project == "env-project"

            # In the ideal system, GoogleAdapter would do:
            # settings = get_settings()
            # project = settings.vertex.project
            # NOT: project = os.getenv("VERTEX_PROJECT")

    def test_logging_system_uses_settings(self):
        """Logging system should use settings for all config."""
        settings = Settings()

        # All these should be configurable through settings
        assert hasattr(settings.logging, "victoria_logs_url")
        assert hasattr(settings.logging, "victoria_logs_enabled")
        assert hasattr(settings.logging, "loki_app_tag")
        assert hasattr(settings.logging, "project_path")

        # Default values
        assert settings.logging.victoria_logs_url == "http://localhost:9428"
        assert settings.logging.victoria_logs_enabled is True
        assert settings.logging.loki_app_tag == "mcp-the-force"

    def test_openai_constants_uses_settings(self):
        """OpenAI constants should use settings."""
        settings = Settings()

        # This should be in settings, not read from env
        assert hasattr(settings.openai, "max_parallel_tool_exec")
        assert settings.openai.max_parallel_tool_exec == 8  # default

    def test_loiter_killer_uses_settings(self):
        """Loiter killer should use settings."""
        settings = Settings()

        # Should be configurable
        assert hasattr(settings.services, "loiter_killer_url")
        assert settings.services.loiter_killer_url == "http://localhost:9876"

    def test_test_flags_in_settings(self):
        """Test flags should be in settings."""
        settings = Settings()

        # Test/dev flags should be configurable
        assert hasattr(settings.dev, "adapter_mock")
        assert hasattr(settings.dev, "ci_e2e")
        assert settings.dev.adapter_mock is False  # default
        assert settings.dev.ci_e2e is False  # default


class TestCompleteConfigurationCoverage:
    """Test that ALL configuration options work through ALL paths."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_all_options_in_yaml(self, tmp_path, monkeypatch):
        """Every configuration option should be settable via YAML."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: 0.0.0.0
  port: 9000
  context_percentage: 0.9
  default_temperature: 0.5

providers:
  openai:
    enabled: true
    api_key: yaml-openai-key
    max_parallel_tool_exec: 16
  vertex:
    enabled: true
    project: yaml-project
    location: yaml-location
  anthropic:
    enabled: false
    api_key: yaml-anthropic-key
  xai:
    enabled: true
    api_key: yaml-xai-key
  litellm:
    enabled: true

logging:
  level: DEBUG
  victoria_logs_enabled: true
  victoria_logs_url: http://custom:9428
  loki_app_tag: custom-tag
  project_path: /custom/path

services:
  loiter_killer_url: http://custom:9876

session:
  ttl_seconds: 7200
  db_path: custom.db
  cleanup_probability: 0.02

memory:
  enabled: true
  rollover_limit: 10000
  session_cutoff_hours: 3
  summary_char_limit: 300000
  max_files_per_commit: 100

security:
  path_blacklist:
    - /etc
    - /custom/blacklist

dev:
  adapter_mock: true
  ci_e2e: false
""")

        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))
        settings = Settings()

        # Every single value should be loaded from YAML
        assert settings.mcp.host == "0.0.0.0"
        assert settings.mcp.port == 9000
        assert settings.mcp.context_percentage == 0.9
        assert settings.mcp.default_temperature == 0.5

        assert settings.openai.api_key == "yaml-openai-key"
        assert settings.openai.max_parallel_tool_exec == 16

        assert settings.logging.victoria_logs_url == "http://custom:9428"
        assert settings.logging.loki_app_tag == "custom-tag"

        assert settings.services.loiter_killer_url == "http://custom:9876"

        assert settings.security.path_blacklist == ["/etc", "/custom/blacklist"]

        assert settings.dev.adapter_mock is True

    def test_all_options_via_env_vars(self, monkeypatch):
        """Every configuration option should be settable via env vars."""
        env_vars = {
            # MCP settings
            "HOST": "env-host",
            "PORT": "9999",
            "CONTEXT_PERCENTAGE": "0.95",
            "DEFAULT_TEMPERATURE": "0.2",
            # Provider settings (both nested and flat)
            "OPENAI__API_KEY": "env-openai-key",
            "OPENAI__MAX_PARALLEL_TOOL_EXEC": "32",
            "VERTEX_PROJECT": "env-project",  # flat legacy
            "VERTEX_LOCATION": "env-location",
            # Logging settings
            "LOGGING__LEVEL": "ERROR",
            "LOGGING__VICTORIA_LOGS_URL": "http://env:9428",
            "LOGGING__VICTORIA_LOGS_ENABLED": "false",
            "LOGGING__LOKI_APP_TAG": "env-tag",
            # Service URLs
            "SERVICES__LOITER_KILLER_URL": "http://env:9876",
            # Session settings
            "SESSION__TTL_SECONDS": "3600",
            # Security settings
            "SECURITY__PATH_BLACKLIST": "['/env1', '/env2']",
            # Dev flags
            "DEV__ADAPTER_MOCK": "1",
            "DEV__CI_E2E": "true",
        }

        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)

        settings = Settings()

        # All values should be loaded from env
        assert settings.mcp.host == "env-host"
        assert settings.mcp.port == 9999
        assert settings.openai.api_key == "env-openai-key"
        assert settings.openai.max_parallel_tool_exec == 32
        assert settings.logging.victoria_logs_url == "http://env:9428"
        assert settings.logging.victoria_logs_enabled is False
        assert settings.services.loiter_killer_url == "http://env:9876"
        assert settings.security.path_blacklist == ["/env1", "/env2"]
        assert settings.dev.adapter_mock is True

    def test_mcp_json_supports_all_options(self, monkeypatch):
        """MCP JSON should support all configuration options."""
        mcp_json = {
            "mcpServers": {
                "the-force": {
                    "env": {
                        "HOST": "mcp-host",
                        "PORT": "6000",
                        "OPENAI__API_KEY": "mcp-key",
                        "LOGGING__VICTORIA_LOGS_URL": "http://mcp:9428",
                        "SERVICES__LOITER_KILLER_URL": "http://mcp:9876",
                        "DEV__ADAPTER_MOCK": "true",
                    }
                }
            }
        }

        monkeypatch.setenv("MCP_CONFIG_JSON", json.dumps(mcp_json))
        settings = Settings()

        assert settings.mcp.host == "mcp-host"
        assert settings.mcp.port == 6000
        assert settings.openai.api_key == "mcp-key"
        assert settings.logging.victoria_logs_url == "http://mcp:9428"
        assert settings.services.loiter_killer_url == "http://mcp:9876"
        assert settings.dev.adapter_mock is True


class TestConfigurationSchema:
    """Test the complete configuration schema."""

    def test_ideal_settings_structure(self):
        """Test the ideal settings class structure."""
        settings = Settings()

        # MCP core settings
        assert hasattr(settings, "mcp")
        assert hasattr(settings.mcp, "host")
        assert hasattr(settings.mcp, "port")
        assert hasattr(settings.mcp, "context_percentage")
        assert hasattr(settings.mcp, "default_temperature")

        # Provider settings
        assert hasattr(settings, "openai")
        assert hasattr(settings.openai, "api_key")
        assert hasattr(settings.openai, "max_parallel_tool_exec")

        assert hasattr(settings, "vertex")
        assert hasattr(settings, "anthropic")
        assert hasattr(settings, "xai")
        assert hasattr(settings, "litellm")

        # Logging settings
        assert hasattr(settings, "logging")
        assert hasattr(settings.logging, "level")
        assert hasattr(settings.logging, "victoria_logs_enabled")
        assert hasattr(settings.logging, "victoria_logs_url")
        assert hasattr(settings.logging, "loki_app_tag")
        assert hasattr(settings.logging, "project_path")

        # Service URLs
        assert hasattr(settings, "services")
        assert hasattr(settings.services, "loiter_killer_url")

        # Session settings
        assert hasattr(settings, "session")
        assert hasattr(settings.session, "ttl_seconds")
        assert hasattr(settings.session, "db_path")

        # Memory settings
        assert hasattr(settings, "memory")
        assert hasattr(settings.memory, "enabled")
        assert hasattr(settings.memory, "rollover_limit")

        # Security settings
        assert hasattr(settings, "security")
        assert hasattr(settings.security, "path_blacklist")

        # Dev/test flags
        assert hasattr(settings, "dev")
        assert hasattr(settings.dev, "adapter_mock")
        assert hasattr(settings.dev, "ci_e2e")


class TestMCPJSONLoader:
    """Test MCP JSON configuration loading."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_mcp_json_from_env_var(self, monkeypatch):
        """Load MCP JSON from MCP_CONFIG_JSON env var."""
        mcp_json = {
            "mcpServers": {
                "the-force": {
                    "command": "uv",
                    "args": ["run", "--", "mcp-the-force"],
                    "env": {"OPENAI_API_KEY": "mcp-json-key", "PORT": "7777"},
                }
            }
        }

        monkeypatch.setenv("MCP_CONFIG_JSON", json.dumps(mcp_json))
        settings = Settings()

        assert settings.openai.api_key == "mcp-json-key"
        assert settings.mcp.port == 7777

    def test_mcp_json_from_file(self, tmp_path, monkeypatch):
        """Load MCP JSON from file path."""
        mcp_json_file = tmp_path / "mcp-config.json"
        mcp_json_file.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "the-force": {
                            "env": {"OPENAI_API_KEY": "file-key", "HOST": "file-host"}
                        }
                    }
                }
            )
        )

        monkeypatch.setenv("MCP_CONFIG_JSON_FILE", str(mcp_json_file))
        settings = Settings()

        assert settings.openai.api_key == "file-key"
        assert settings.mcp.host == "file-host"

    def test_mcp_json_nested_env_vars(self, monkeypatch):
        """MCP JSON should support nested env var format."""
        mcp_json = {
            "mcpServers": {
                "the-force": {
                    "env": {
                        "OPENAI__API_KEY": "nested-key",
                        "LOGGING__LEVEL": "DEBUG",
                        "SERVICES__LOITER_KILLER_URL": "http://mcp:9999",
                    }
                }
            }
        }

        monkeypatch.setenv("MCP_CONFIG_JSON", json.dumps(mcp_json))
        settings = Settings()

        assert settings.openai.api_key == "nested-key"
        assert settings.logging.level == "DEBUG"
        assert settings.services.loiter_killer_url == "http://mcp:9999"


class TestBackwardCompatibility:
    """Test backward compatibility is maintained."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_flat_properties_still_work(self):
        """Flat properties should still work for backward compatibility."""
        settings = Settings()

        # These should work as aliases
        settings.openai.api_key = "test-key"
        assert settings.openai_api_key == "test-key"

        settings.vertex.project = "test-project"
        assert settings.vertex_project == "test-project"

    def test_legacy_env_vars_still_work(self, monkeypatch):
        """Legacy flat env vars should still work."""
        monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
        monkeypatch.setenv("VERTEX_PROJECT", "legacy-project")

        settings = Settings()

        # Should work through backward compatibility
        assert settings.openai.api_key == "legacy-key"
        assert settings.vertex.project == "legacy-project"


class TestConfigurationValidation:
    """Test configuration validation and error handling."""

    def test_invalid_mcp_json_format(self, monkeypatch):
        """Invalid MCP JSON should raise clear error."""
        monkeypatch.setenv("MCP_CONFIG_JSON", "invalid json")

        with pytest.raises(ValueError, match="Invalid MCP JSON"):
            Settings()

    def test_missing_required_structure_in_mcp_json(self, monkeypatch):
        """MCP JSON missing required structure should be handled."""
        mcp_json = {"wrongKey": "value"}

        monkeypatch.setenv("MCP_CONFIG_JSON", json.dumps(mcp_json))

        # Should not crash, just ignore invalid structure
        settings = Settings()
        assert settings.mcp.port == 8000  # default

    def test_type_coercion_in_all_sources(self, tmp_path, monkeypatch):
        """Type coercion should work across all config sources."""
        # YAML with string numbers
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  port: "8001"
openai:
  max_parallel_tool_exec: "16"
memory:
  enabled: "true"
""")

        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))
        settings = Settings()

        assert settings.mcp.port == 8001  # converted to int
        assert settings.openai.max_parallel_tool_exec == 16  # converted to int
        assert settings.memory.enabled is True  # converted to bool


class TestSingletonBehavior:
    """Test settings singleton behavior."""

    def test_get_settings_returns_singleton(self):
        """get_settings() should return the same instance."""
        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_settings_immutable_after_creation(self):
        """Settings should be effectively immutable after creation."""
        settings = get_settings()

        # Direct modification should not affect subsequent calls
        original_port = settings.mcp.port
        settings.mcp.port = 9999

        # New call should have original value
        get_settings.cache_clear()
        new_settings = get_settings()
        assert new_settings.mcp.port == original_port


class TestEnvironmentIsolation:
    """Test that configuration is properly isolated in tests."""

    def test_no_env_leak_between_tests(self, monkeypatch):
        """Environment changes should not leak between tests."""
        # This test relies on proper setup_method clearing cache
        monkeypatch.setenv("OPENAI_API_KEY", "test-specific-key")

        settings = Settings()
        assert settings.openai.api_key == "test-specific-key"

        # In next test, this should not persist

    def test_yaml_files_ignored_in_tests_by_default(self, tmp_path, monkeypatch):
        """YAML files should be ignored in test environment unless explicit."""
        # Create config in current directory
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  port: 9999
""")

        monkeypatch.chdir(tmp_path)

        # Without explicit env var, should use defaults in tests
        settings = Settings()
        assert settings.mcp.port == 8000  # default, not from YAML


# Future considerations for the ideal system:
# 1. Runtime config reloading (watch files, reload on SIGHUP)
# 2. Config validation on startup with clear error messages
# 3. Config migration tooling for version upgrades
# 4. Encrypted secrets support (e.g., via SOPS or similar)
# 5. Multi-environment support (dev/staging/prod profiles)
