"""
Edge case and integration tests for configuration system.
"""

import os
import yaml
import pytest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from mcp_the_force.config import Settings, get_settings, _deep_merge


class TestConfigurationEdgeCases:
    """Test edge cases and error scenarios."""

    def setup_method(self):
        """Clear settings cache and environment before each test."""
        from mcp_the_force.config import get_settings

        get_settings.cache_clear()

    def test_empty_yaml_files(self, tmp_path, monkeypatch):
        """Test handling of empty YAML files."""
        # Create empty files
        (tmp_path / "config.yaml").write_text("")
        (tmp_path / "secrets.yaml").write_text("")

        monkeypatch.setenv("MCP_CONFIG_FILE", str(tmp_path / "config.yaml"))
        monkeypatch.setenv("MCP_SECRETS_FILE", str(tmp_path / "secrets.yaml"))

        # Should use defaults
        settings = Settings()
        assert settings.mcp.host == "127.0.0.1"
        assert settings.mcp.port == 8000

    def test_yaml_with_none_values(self, tmp_path, monkeypatch):
        """Test YAML files with null/None values."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: "127.0.0.1"  # Can't be null
  port: 8000  # Can't be null
providers:
  openai:
    api_key: null  # This can be null
""")

        # Change to temp directory to avoid loading .env file
        monkeypatch.chdir(tmp_path)

        # Clear environment to prevent leaking
        with patch.dict(os.environ, {"MCP_CONFIG_FILE": str(config_yaml)}, clear=True):
            get_settings.cache_clear()

            settings = Settings()
            # Required fields use provided values
            assert settings.mcp.host == "127.0.0.1"
            assert settings.mcp.port == 8000
            # Optional fields can be None
            assert settings.openai.api_key is None

    def test_yaml_with_special_characters(self, tmp_path, monkeypatch):
        """Test YAML with special characters and escaping."""
        secrets_yaml = tmp_path / "secrets.yaml"
        # Use proper YAML syntax for special characters
        secrets_yaml.write_text("""
providers:
  openai:
    api_key: "sk-proj$pecial!@#chars&symbols"
  anthropic:
    api_key: "quotes\\\"and'apostrophes"
""")

        # Clear environment to prevent real API keys from leaking in
        with patch.dict(os.environ, {}, clear=True):
            monkeypatch.setenv("MCP_SECRETS_FILE", str(secrets_yaml))
            get_settings.cache_clear()

            settings = Settings()
            assert settings.openai.api_key == "sk-proj$pecial!@#chars&symbols"
            assert settings.anthropic.api_key == "quotes\"and'apostrophes"

    def test_circular_reference_protection(self):
        """Test protection against circular references in deep merge."""
        # Create circular reference
        a = {"parent": {"child": {}}}
        a["parent"]["child"]["back"] = a["parent"]

        b = {"parent": {"child": {"value": "test"}}}

        # Should not crash with circular reference
        result = _deep_merge(a, b)
        assert result["parent"]["child"]["value"] == "test"

    def test_extremely_nested_configuration(self, tmp_path, monkeypatch):
        """Test handling of deeply nested configuration."""
        # Create deeply nested config
        nested_config = {"level1": {}}
        current = nested_config["level1"]
        for i in range(2, 20):
            current[f"level{i}"] = {}
            current = current[f"level{i}"]
        current["value"] = "deep_value"

        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(yaml.dump(nested_config))

        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        # Should handle deep nesting
        settings = Settings()
        # Config loaded successfully
        assert settings.mcp.host == "127.0.0.1"

    def test_unicode_in_configuration(self, tmp_path, monkeypatch):
        """Test Unicode characters in configuration."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text(
            """
mcp:
  host: "127.0.0.1"
providers:
  openai:
    api_key: "测试密钥🔑"
  vertex:
    project: "プロジェクト"
    location: "歐洲-西部1"
""",
            encoding="utf-8",
        )

        # Change to temp directory to avoid loading .env file
        monkeypatch.chdir(tmp_path)

        # Clear environment to prevent real API keys from leaking in
        with patch.dict(os.environ, {"MCP_CONFIG_FILE": str(config_yaml)}, clear=True):
            get_settings.cache_clear()

            settings = Settings()
            assert settings.openai.api_key == "测试密钥🔑"
            assert settings.vertex.project == "プロジェクト"
            assert settings.vertex.location == "歐洲-西部1"

    def test_file_permission_errors(self, tmp_path, monkeypatch):
        """Test handling of file permission errors."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("mcp:\n  port: 8000")

        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        # Simulate permission error
        with patch("builtins.open", side_effect=PermissionError("No read permission")):
            # Should fall back to defaults
            settings = Settings()
            assert settings.mcp.port == 8000  # default

    def test_concurrent_settings_access(self):
        """Test thread-safe concurrent access to settings."""
        results = []
        errors = []

        def access_settings():
            try:
                settings = get_settings()
                results.append(settings.mcp.port)
            except Exception as e:
                errors.append(e)

        # Clear cache to start fresh
        get_settings.cache_clear()

        # Access settings from multiple threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(access_settings) for _ in range(50)]
            for future in futures:
                future.result()

        # All accesses should succeed
        assert len(errors) == 0
        assert len(results) == 50
        assert all(port == 8000 for port in results)

    def test_environment_variable_type_coercion(self):
        """Test type coercion for environment variables."""
        test_cases = [
            # Boolean coercion
            ("MEMORY_ENABLED", "true", lambda s: s.history.enabled is True),
            ("MEMORY_ENABLED", "TRUE", lambda s: s.history.enabled is True),
            ("MEMORY_ENABLED", "1", lambda s: s.history.enabled is True),
            ("MEMORY_ENABLED", "false", lambda s: s.history.enabled is False),
            ("MEMORY_ENABLED", "FALSE", lambda s: s.history.enabled is False),
            ("MEMORY_ENABLED", "0", lambda s: s.history.enabled is False),
            # Integer coercion
            ("PORT", "8080", lambda s: s.mcp.port == 8080),
            ("SESSION_TTL_SECONDS", "7200", lambda s: s.session.ttl_seconds == 7200),
            # Float coercion
            ("CONTEXT_PERCENTAGE", "0.75", lambda s: s.mcp.context_percentage == 0.75),
            (
                "DEFAULT_TEMPERATURE",
                "0.123",
                lambda s: s.mcp.default_temperature == 0.123,
            ),
        ]

        for env_var, value, assertion in test_cases:
            with patch.dict(os.environ, {env_var: value}, clear=True):
                get_settings.cache_clear()
                settings = Settings()
                assert assertion(settings), f"Failed for {env_var}={value}"

    def test_malformed_env_values(self):
        """Test handling of malformed environment variable values."""
        # Invalid boolean
        with patch.dict(os.environ, {"MEMORY_ENABLED": "maybe"}, clear=True):
            with pytest.raises(ValueError):
                Settings()

        # Invalid integer
        with patch.dict(os.environ, {"PORT": "abc"}, clear=True):
            with pytest.raises(ValueError):
                Settings()

        # Invalid float
        with patch.dict(os.environ, {"CONTEXT_PERCENTAGE": "not-a-float"}, clear=True):
            with pytest.raises(ValueError):
                Settings()


class TestConfigurationIntegration:
    """Integration tests for the configuration system."""

    def setup_method(self):
        """Clear settings cache and environment before each test."""
        from mcp_the_force.config import get_settings

        get_settings.cache_clear()

    def test_full_configuration_stack(self, tmp_path, monkeypatch):
        """Test complete configuration loading with all sources."""
        monkeypatch.chdir(tmp_path)

        # 1. Create .env file (lowest priority)
        env_file = tmp_path / ".env"
        env_file.write_text("""
HOST=env-host
PORT=7000
OPENAI_API_KEY=env-key
LOG_LEVEL=INFO
""")

        # 2. Create config.yaml (middle priority)
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: yaml-host
  port: 8000
  context_percentage: 0.9
logging:
  level: WARNING
providers:
  vertex:
    project: yaml-project
""")

        # 3. Create secrets.yaml (merges with config.yaml)
        secrets_yaml = tmp_path / "secrets.yaml"
        secrets_yaml.write_text("""
providers:
  openai:
    api_key: yaml-secret-key
  anthropic:
    api_key: anthropic-secret
""")

        # 4. Set environment variables (highest priority)
        # Use clear=True to prevent real env vars from leaking
        with patch.dict(
            os.environ,
            {
                "MCP_CONFIG_FILE": str(config_yaml),
                "MCP_SECRETS_FILE": str(secrets_yaml),
                "PORT": "9000",  # Overrides both .env and yaml
                "VERTEX_LOCATION": "env-location",  # Only in env
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()

            # Test precedence
            assert settings.mcp.host == "yaml-host"  # yaml > .env
            assert settings.mcp.port == 9000  # env > yaml > .env
            assert settings.openai.api_key == "yaml-secret-key"  # secrets.yaml > .env
            assert settings.logging.level == "WARNING"  # yaml > .env
            assert settings.mcp.context_percentage == 0.9  # only in yaml
            assert settings.vertex.project == "yaml-project"  # only in yaml
            assert settings.vertex.location == "env-location"  # only in env
            assert settings.anthropic.api_key == "anthropic-secret"  # only in secrets

    def test_configuration_migration_scenario(self, tmp_path, monkeypatch):
        """Test realistic migration from legacy to new configuration."""
        monkeypatch.chdir(tmp_path)

        # 1. Load with legacy environment variables (no .env support)
        legacy_env = {
            "OPENAI_API_KEY": "legacy-openai-key",
            "VERTEX_PROJECT": "legacy-project",
            "VERTEX_LOCATION": "us-central1",
            "PORT": "8000",
            "MEMORY_ENABLED": "true",
            "MEMORY_ROLLOVER_LIMIT": "5000",
            "SESSION_TTL_SECONDS": "3600",
            "LOG_LEVEL": "INFO",
        }

        with patch.dict(os.environ, legacy_env, clear=True):
            get_settings.cache_clear()
            settings = Settings()
            assert settings.openai.api_key == "legacy-openai-key"
            assert settings.history.rollover_limit == 5000

        # 2. Migrate to new YAML configuration
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  port: 8080  # Different from .env
logging:
  level: DEBUG  # Different from .env
history:
  enabled: true
  rollover_limit: 7500  # Different from .env
session:
  ttl_seconds: 7200  # Different from .env
providers:
  vertex:
    project: yaml-project  # Different from .env
    location: us-central1
""")

        secrets_yaml = tmp_path / "secrets.yaml"
        secrets_yaml.write_text("""
providers:
  openai:
    api_key: yaml-openai-key  # Different from .env
""")

        # 3. Load with both legacy and new config (new should win)
        with patch.dict(
            os.environ,
            {
                "MCP_CONFIG_FILE": str(config_yaml),
                "MCP_SECRETS_FILE": str(secrets_yaml),
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()

            # YAML values should override .env
            assert settings.mcp.port == 8080
            assert settings.openai.api_key == "yaml-openai-key"
            assert settings.history.rollover_limit == 7500
            assert settings.session.ttl_seconds == 7200
            assert settings.vertex.project == "yaml-project"
            assert settings.logging.level == "DEBUG"

    def test_partial_configuration_override(self, tmp_path, monkeypatch):
        """Test partial override of nested configuration."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: 0.0.0.0
  port: 8000
  context_percentage: 0.85
  default_temperature: 0.2
providers:
  openai:
    enabled: true
    api_key: base-key
  vertex:
    enabled: true
    project: base-project
    location: us-central1
history:
  enabled: true
  rollover_limit: 9500
  session_cutoff_hours: 2
""")

        secrets_yaml = tmp_path / "secrets.yaml"
        secrets_yaml.write_text("""
providers:
  openai:
    api_key: secret-key  # Override just the API key
""")

        # Add a single env var override
        with patch.dict(
            os.environ,
            {
                "MCP_CONFIG_FILE": str(config_yaml),
                "MCP_SECRETS_FILE": str(secrets_yaml),
                "MEMORY_ROLLOVER_LIMIT": "10000",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()

            # Check partial overrides
            assert settings.openai.enabled is True  # from config.yaml
            assert settings.openai.api_key == "secret-key"  # from secrets.yaml
            assert settings.vertex.project == "base-project"  # from config.yaml
            assert settings.history.rollover_limit == 10000  # from env
            assert settings.history.session_cutoff_hours == 2  # from config.yaml

    def test_configuration_with_real_world_values(self, tmp_path, monkeypatch):
        """Test configuration with realistic production values."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  host: 0.0.0.0
  port: 8080
  context_percentage: 0.85
  default_temperature: 0.2

logging:
  level: INFO

providers:
  openai:
    enabled: true
  vertex:
    enabled: true
    project: my-production-project
    location: us-central1
  anthropic:
    enabled: false

session:
  ttl_seconds: 3600
  db_path: /var/lib/mcp/sessions.db
  cleanup_probability: 0.01

history:
  enabled: true
  rollover_limit: 9500
  session_cutoff_hours: 2
  summary_char_limit: 200000
  max_files_per_commit: 50
""")

        secrets_yaml = tmp_path / "secrets.yaml"
        secrets_yaml.write_text("""
providers:
  openai:
    api_key: sk-proj-abcdefghijklmnopqrstuvwxyz123456789
  anthropic:
    api_key: claude-ai-abcdefghijklmnopqrstuvwxyz123456789
""")

        with patch.dict(
            os.environ,
            {
                "MCP_CONFIG_FILE": str(config_yaml),
                "MCP_SECRETS_FILE": str(secrets_yaml),
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()

            # Verify all values loaded correctly
            assert settings.mcp.host == "0.0.0.0"
            assert settings.mcp.port == 8080
            assert settings.openai.api_key.startswith("sk-proj-")
            assert settings.vertex.project == "my-production-project"
            assert settings.session.db_path == "/var/lib/mcp/sessions.db"
            assert settings.history.summary_char_limit == 200000

            # Test export functionality with real values
            env_vars = settings.export_env()
            assert env_vars["OPENAI_API_KEY"].startswith("sk-proj-")
            assert env_vars["SESSION_DB_PATH"] == "/var/lib/mcp/sessions.db"

            mcp_config = settings.export_mcp_config()
            assert mcp_config["mcpServers"]["the-force"]["env"]["PORT"] == "8080"
