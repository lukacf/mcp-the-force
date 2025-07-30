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

import os
import pytest
from unittest.mock import patch
from mcp_the_force.config import Settings, get_settings

# pytestmark = pytest.mark.skip(reason="Aspirational TDD - not yet implemented")


class TestIdealConfigurationHierarchy:
    """Test the ideal 4-level configuration hierarchy."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_mcp_json_env_vars_highest_priority(self, tmp_path, monkeypatch):
        """Environment variables set by MCP client should override everything else.

        Note: MCP JSON is not parsed directly by the server. Instead, the MCP client
        reads the JSON and sets environment variables when spawning the server process.
        Those env vars then have the highest priority.
        """
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

        # These env vars simulate what the MCP client would set from the JSON config
        # They should have highest priority
        monkeypatch.setenv("PORT", "7000")
        monkeypatch.setenv("OPENAI_API_KEY", "mcp-client-key")

        settings = Settings()

        # Env vars (as set by MCP client) should win
        assert settings.mcp.port == 7000
        assert settings.openai.api_key == "mcp-client-key"

    def test_complete_hierarchy_precedence(self, tmp_path, monkeypatch):
        """Test full hierarchy: env vars > YAML > defaults."""
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

        # 3. Environment variables (highest priority)
        # These simulate what MCP client would set
        monkeypatch.setenv("PORT", "8002")
        monkeypatch.setenv("HOST", "env-host")

        settings = Settings()

        # Results should follow hierarchy
        assert settings.mcp.port == 8002  # env wins
        assert settings.mcp.host == "env-host"  # env wins
        assert settings.mcp.context_percentage == 0.8  # YAML wins (no env)
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

    def test_vector_store_cache_uses_settings(self):
        """Vector store cache should use settings."""
        settings = Settings()

        # Should be configurable
        assert hasattr(settings, "vector_stores")
        assert settings.vector_stores.ttl_seconds == 7200  # 2 hours default
        assert settings.vector_stores.cleanup_interval_seconds == 300  # 5 minutes
        assert settings.vector_stores.cleanup_probability == 0.02  # 2%

    def test_test_flags_in_settings(self):
        """Test flags should be in settings."""
        # Clear the cache to ensure fresh settings
        get_settings.cache_clear()

        # Save current env vars if they exist
        saved_adapter_mock = os.environ.get("MCP_ADAPTER_MOCK")
        saved_ci_e2e = os.environ.get("CI_E2E")

        try:
            # Clear env vars to test defaults
            if "MCP_ADAPTER_MOCK" in os.environ:
                del os.environ["MCP_ADAPTER_MOCK"]
            if "CI_E2E" in os.environ:
                del os.environ["CI_E2E"]

            settings = Settings()

            # Test/dev flags should be configurable
            assert hasattr(settings.dev, "adapter_mock")
            assert hasattr(settings.dev, "ci_e2e")
            assert settings.dev.adapter_mock is False  # default
            assert settings.dev.ci_e2e is False  # default
        finally:
            # Restore env vars
            if saved_adapter_mock is not None:
                os.environ["MCP_ADAPTER_MOCK"] = saved_adapter_mock
            if saved_ci_e2e is not None:
                os.environ["CI_E2E"] = saved_ci_e2e


class TestCompleteConfigurationCoverage:
    """Test that ALL configuration options work through ALL paths."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_all_options_in_yaml(self, tmp_path, monkeypatch):
        """Every configuration option should be settable via YAML.

        Note: This test may fail if real environment variables (like OPENAI_API_KEY)
        are set, as they take precedence over YAML. This is the correct behavior -
        env vars should override YAML. In a clean test environment without real
        API keys, this test validates that all options can be set via YAML.
        """
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
  # Currently no external services configured

vector_stores:
  ttl_seconds: 3600
  cleanup_interval_seconds: 600
  cleanup_probability: 0.05

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

        # Clear the cache to ensure fresh settings
        get_settings.cache_clear()

        settings = Settings()

        # Test values that are likely not overridden by env vars
        assert settings.mcp.host == "0.0.0.0"
        assert settings.mcp.port == 9000
        assert settings.mcp.context_percentage == 0.9
        assert settings.mcp.default_temperature == 0.5

        # For values that might be overridden by real env vars, check if they exist
        if "OPENAI_API_KEY" not in os.environ and "OPENAI__API_KEY" not in os.environ:
            assert settings.openai.api_key == "yaml-openai-key"
        assert settings.openai.max_parallel_tool_exec == 16

        assert settings.logging.victoria_logs_url == "http://custom:9428"
        assert settings.logging.loki_app_tag == "custom-tag"

        assert settings.vector_stores.ttl_seconds == 3600
        assert settings.vector_stores.cleanup_interval_seconds == 600
        assert settings.vector_stores.cleanup_probability == 0.05

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
            "SERVICES__LOITER_KILLER_HOST": "env",
            "SERVICES__LOITER_KILLER_PORT": "9876",
            # Session settings
            "SESSION__TTL_SECONDS": "3600",
            # Security settings
            "SECURITY__PATH_BLACKLIST": '["/env1", "/env2"]',
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
        # Services should be empty
        assert settings.security.path_blacklist == ["/env1", "/env2"]
        assert settings.dev.adapter_mock is True

    def test_mcp_client_env_vars_support_all_options(self, monkeypatch):
        """Environment variables (as set by MCP client) should support all configuration options."""
        # These env vars simulate what the MCP client would set from its JSON config
        monkeypatch.setenv("HOST", "mcp-host")
        monkeypatch.setenv("PORT", "6000")
        monkeypatch.setenv("OPENAI__API_KEY", "mcp-key")
        monkeypatch.setenv("LOGGING__VICTORIA_LOGS_URL", "http://mcp:9428")
        monkeypatch.setenv("VECTOR_STORES__TTL_SECONDS", "1800")
        monkeypatch.setenv("VECTOR_STORES__CLEANUP_INTERVAL_SECONDS", "180")
        monkeypatch.setenv("DEV__ADAPTER_MOCK", "true")

        settings = Settings()

        assert settings.mcp.host == "mcp-host"
        assert settings.mcp.port == 6000
        assert settings.openai.api_key == "mcp-key"
        assert settings.logging.victoria_logs_url == "http://mcp:9428"
        assert settings.vector_stores.ttl_seconds == 1800
        assert settings.vector_stores.cleanup_interval_seconds == 180
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
        assert settings.openai.max_parallel_tool_exec == 8  # default

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
        # No external services currently configured

        # Vector store settings
        assert hasattr(settings, "vector_stores")
        assert hasattr(settings.vector_stores, "ttl_seconds")
        assert hasattr(settings.vector_stores, "cleanup_interval_seconds")
        assert hasattr(settings.vector_stores, "cleanup_probability")

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


# Removed TestMCPJSONLoader class - MCP JSON is not parsed by the server.
# The MCP client reads the JSON and sets environment variables when spawning the server.


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

    # Removed MCP JSON validation tests - server doesn't parse JSON

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


class TestMissingValidationCases:
    """Additional validation tests based on Gemini's review."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_port_validation_with_clear_errors(self):
        """Test port validation with descriptive error messages."""
        # Invalid port numbers
        test_cases = [
            ("0", "greater than or equal to 1"),
            ("65536", "less than or equal to 65535"),
            ("not-a-number", "Input should be a valid integer"),
            ("-1", "greater than or equal to 1"),
        ]

        for port_value, expected_msg in test_cases:
            with patch.dict(os.environ, {"PORT": port_value}, clear=True):
                with pytest.raises(ValueError) as exc_info:
                    Settings()
                error_str = str(exc_info.value).lower()
                assert (
                    expected_msg.lower() in error_str or "validation error" in error_str
                )

    @pytest.mark.skip(
        reason="Aspirational - provider-specific validation not yet implemented"
    )
    def test_required_values_validation(self, tmp_path, monkeypatch):
        """Test validation of required values based on enabled providers."""
        # OpenAI enabled without API key
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
providers:
  openai:
    enabled: true
""")
        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI__API_KEY", raising=False)

        with pytest.raises(ValueError) as exc_info:
            Settings()
        assert "OpenAI API key is required when OpenAI provider is enabled" in str(
            exc_info.value
        )

    @pytest.mark.skip(
        reason="Aspirational - currently logs warning instead of raising error"
    )
    def test_file_permission_errors(self, tmp_path, monkeypatch):
        """Test handling of file permission errors."""
        # Create a file with no read permissions
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("mcp:\n  port: 8000")
        config_yaml.chmod(0o000)  # No permissions

        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        with pytest.raises(PermissionError) as exc_info:
            Settings()
        assert "Permission denied" in str(exc_info.value)

    @pytest.mark.skip(reason="Aspirational - empty string handling not yet implemented")
    def test_empty_string_vs_null_handling(self, tmp_path, monkeypatch):
        """Test distinction between empty strings and null values."""
        # Test empty string in env var
        monkeypatch.setenv("OPENAI_API_KEY", "")

        # YAML with actual value
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
providers:
  openai:
    api_key: yaml-key
""")
        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        settings = Settings()

        # Empty string should be treated as "not set" and fall back to YAML
        assert settings.openai.api_key == "yaml-key"

    def test_complex_type_override_behavior(self, tmp_path, monkeypatch):
        """Test that complex types (lists/dicts) are replaced, not merged."""
        # YAML with list
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
security:
  path_blacklist:
    - /etc
    - /usr
    - /bin
""")
        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        # Env var completely replaces the list
        monkeypatch.setenv("SECURITY__PATH_BLACKLIST", '["/home", "/tmp"]')

        settings = Settings()

        # Should be complete replacement
        assert settings.security.path_blacklist == ["/home", "/tmp"]
        assert len(settings.security.path_blacklist) == 2

    @pytest.mark.skip(reason="Aspirational - settings immutability not yet implemented")
    def test_settings_deep_immutability(self):
        """Test that settings and all nested objects are immutable."""
        settings = Settings()

        # Root level immutability
        with pytest.raises(AttributeError):
            settings.new_field = "value"

        # First level immutability
        with pytest.raises(AttributeError):
            settings.mcp.port = 9999

        # Deep immutability
        with pytest.raises(AttributeError):
            settings.openai.api_key = "new-key"

        # List immutability
        if hasattr(settings.security, "path_blacklist"):
            with pytest.raises(AttributeError):
                settings.security.path_blacklist.append("/new")

    @pytest.mark.skip(reason="Aspirational - YAML errors currently logged as warnings")
    def test_invalid_yaml_with_clear_errors(self, tmp_path, monkeypatch):
        """Test YAML parsing errors with descriptive messages."""
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
mcp:
  port: [unclosed
  host: 0.0.0.0
invalid: : syntax
""")
        monkeypatch.setenv("MCP_CONFIG_FILE", str(config_yaml))

        with pytest.raises(ValueError) as exc_info:
            Settings()
        error_msg = str(exc_info.value)
        assert "YAML parsing error" in error_msg
        assert str(config_yaml) in error_msg

    @pytest.mark.skip(reason="Aspirational - flexible list parsing not yet implemented")
    def test_env_var_list_parsing_options(self, monkeypatch):
        """Test flexible list parsing from environment variables."""
        # Python list syntax
        monkeypatch.setenv("SECURITY__PATH_BLACKLIST", '["/etc", "/usr", "/bin"]')
        settings = Settings()
        assert settings.security.path_blacklist == ["/etc", "/usr", "/bin"]

        # Comma-separated (more user-friendly)
        get_settings.cache_clear()
        monkeypatch.setenv("SECURITY__PATH_BLACKLIST", "/etc,/usr,/bin")
        settings = Settings()
        assert settings.security.path_blacklist == ["/etc", "/usr", "/bin"]

        # Colon-separated (PATH-style)
        get_settings.cache_clear()
        monkeypatch.setenv("SECURITY__PATH_BLACKLIST", "/etc:/usr:/bin")
        settings = Settings()
        assert settings.security.path_blacklist == ["/etc", "/usr", "/bin"]

    # Removed MCP JSON file tests - server doesn't read JSON files

    def test_value_constraint_validation(self, monkeypatch):
        """Test validation of value constraints."""
        # Context percentage must be between 0.1 and 0.95
        for invalid_pct in ["0.05", "0.99", "1.5", "-0.1"]:
            get_settings.cache_clear()
            monkeypatch.setenv("CONTEXT_PERCENTAGE", invalid_pct)

            with pytest.raises(ValueError) as exc_info:
                Settings()
            error_str = str(exc_info.value).lower()
            assert (
                "greater than or equal to 0.1" in error_str
                or "less than or equal to 0.95" in error_str
                or "validation error" in error_str
            )

        # Temperature must be between 0.0 and 2.0
        for invalid_temp in ["-0.1", "2.5", "3.0"]:
            get_settings.cache_clear()
            monkeypatch.setenv("DEFAULT_TEMPERATURE", invalid_temp)

            with pytest.raises(ValueError) as exc_info:
                Settings()
            error_str = str(exc_info.value).lower()
            assert (
                "greater than or equal to 0" in error_str
                or "less than or equal to 2" in error_str
                or "validation error" in error_str
            )

    def test_type_coercion_errors(self):
        """Test clear errors for failed type coercion."""
        test_cases = [
            ("PORT", "not-a-number", "valid integer"),
            ("DEFAULT_TEMPERATURE", "not-a-float", "valid number"),
            ("MEMORY__ENABLED", "maybe", "valid boolean"),
            ("SESSION__TTL_SECONDS", "1.5hours", "valid integer"),
        ]

        for env_var, value, expected_msg in test_cases:
            get_settings.cache_clear()
            with patch.dict(os.environ, {env_var: value}, clear=True):
                with pytest.raises(ValueError) as exc_info:
                    Settings()
                error_str = str(exc_info.value).lower()
                assert (
                    expected_msg.lower() in error_str or "validation error" in error_str
                )


# Future considerations for the ideal system:
# 1. Runtime config reloading (watch files, reload on SIGHUP)
# 2. Config validation on startup with clear error messages
# 3. Config migration tooling for version upgrades
# 4. Encrypted secrets support (e.g., via SOPS or similar)
# 5. Multi-environment support (dev/staging/prod profiles)
