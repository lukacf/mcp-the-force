"""
Unit tests for mcp-config CLI tool.
"""

import os
import json
import yaml
from unittest.mock import patch
from typer.testing import CliRunner
from mcp_second_brain.cli.config_cli import app
from mcp_second_brain.config import get_settings


runner = CliRunner()


class TestConfigCLI:
    """Test mcp-config CLI commands."""

    def setup_method(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_init_command(self, tmp_path, monkeypatch):
        """Test init command creates config files."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert "[OK] Created config.yaml" in result.stdout
        assert "[OK] Created secrets.yaml" in result.stdout

        # Check files were created
        assert (tmp_path / "config.yaml").exists()
        assert (tmp_path / "secrets.yaml").exists()

        # Check file permissions on secrets.yaml (should be 600)
        secrets_stat = (tmp_path / "secrets.yaml").stat()
        assert oct(secrets_stat.st_mode)[-3:] == "600"

        # Verify YAML content is valid
        with open(tmp_path / "config.yaml") as f:
            config = yaml.safe_load(f)
            assert "mcp" in config
            assert config["mcp"]["host"] == "127.0.0.1"
            assert config["mcp"]["port"] == 8000

        with open(tmp_path / "secrets.yaml") as f:
            secrets = yaml.safe_load(f)
            assert "providers" in secrets
            assert secrets["providers"]["openai"]["api_key"] == ""

    def test_init_command_existing_files(self, tmp_path, monkeypatch):
        """Test init command with existing files."""
        monkeypatch.chdir(tmp_path)

        # Create existing files
        (tmp_path / "config.yaml").write_text("existing: config")
        (tmp_path / "secrets.yaml").write_text("existing: secrets")

        # Without --force, should skip
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "[SKIP] Skipping config.yaml (already exists)" in result.stdout
        assert "[SKIP] Skipping secrets.yaml (already exists)" in result.stdout

        # Verify files weren't overwritten
        assert (tmp_path / "config.yaml").read_text() == "existing: config"

        # With --force, should overwrite
        result = runner.invoke(app, ["init", "--force"])
        assert result.exit_code == 0
        assert "[OK] Created config.yaml" in result.stdout
        assert "[OK] Created secrets.yaml" in result.stdout

        # Verify files were overwritten
        assert (tmp_path / "config.yaml").read_text() != "existing: config"

    def test_validate_command_valid(self, tmp_path, monkeypatch):
        """Test validate command with valid configuration."""
        monkeypatch.chdir(tmp_path)

        # Create valid config
        (tmp_path / "config.yaml").write_text("""
mcp:
  port: 8000
  context_percentage: 0.85
providers:
  openai:
    api_key: test-key
""")

        with patch.dict(
            os.environ, {"MCP_CONFIG_FILE": str(tmp_path / "config.yaml")}, clear=True
        ):
            get_settings.cache_clear()
            result = runner.invoke(app, ["validate"])

        assert result.exit_code == 0
        assert "[OK] Configuration is valid!" in result.stdout

    def test_validate_command_invalid(self, tmp_path, monkeypatch):
        """Test validate command with invalid configuration."""
        monkeypatch.chdir(tmp_path)

        # Create invalid config
        (tmp_path / "config.yaml").write_text("""
mcp:
  port: 99999  # Invalid port
logging:
  level: INVALID_LEVEL
""")

        with patch.dict(
            os.environ, {"MCP_CONFIG_FILE": str(tmp_path / "config.yaml")}, clear=True
        ):
            get_settings.cache_clear()
            result = runner.invoke(app, ["validate"])

        assert result.exit_code == 1
        assert "[ERROR] Configuration validation failed" in result.stdout

    def test_validate_command_missing_api_keys(self, tmp_path, monkeypatch):
        """Test validate command warns about missing API keys."""
        monkeypatch.chdir(tmp_path)

        # Create config without API keys
        (tmp_path / "config.yaml").write_text("""
mcp:
  port: 8000
""")

        with patch.dict(
            os.environ, {"MCP_CONFIG_FILE": str(tmp_path / "config.yaml")}, clear=True
        ):
            result = runner.invoke(app, ["validate"])

        assert result.exit_code == 0
        assert "[WARN] Warning: Missing API keys" in result.stdout
        assert "OPENAI_API_KEY" in result.stdout

    def test_export_env_command(self, tmp_path, monkeypatch):
        """Test export-env command."""
        monkeypatch.chdir(tmp_path)

        # Create config
        (tmp_path / "config.yaml").write_text("""
mcp:
  host: 0.0.0.0
  port: 9000
providers:
  openai:
    api_key: test-openai-key
  vertex:
    project: test-project
    location: us-west1
""")

        with patch.dict(
            os.environ, {"MCP_CONFIG_FILE": str(tmp_path / "config.yaml")}, clear=True
        ):
            get_settings.cache_clear()
            # Default output
            result = runner.invoke(app, ["export-env"])
            assert result.exit_code == 0
            assert (tmp_path / ".env").exists()

            env_content = (tmp_path / ".env").read_text()
            assert "HOST=0.0.0.0" in env_content
            assert "PORT=9000" in env_content
            assert "OPENAI_API_KEY=test-openai-key" in env_content
            assert "VERTEX_PROJECT=test-project" in env_content

            # Custom output path
            get_settings.cache_clear()
            result = runner.invoke(app, ["export-env", "--output", "custom.env"])
            assert result.exit_code == 0
            assert (tmp_path / "custom.env").exists()

    def test_export_client_command(self, tmp_path, monkeypatch):
        """Test export-client command."""
        monkeypatch.chdir(tmp_path)

        # Create config
        (tmp_path / "config.yaml").write_text("""
mcp:
  port: 8080
providers:
  openai:
    api_key: test-key
""")

        with patch.dict(
            os.environ, {"MCP_CONFIG_FILE": str(tmp_path / "config.yaml")}, clear=True
        ):
            get_settings.cache_clear()
            result = runner.invoke(app, ["export-client"])
            assert result.exit_code == 0
            assert (tmp_path / "mcp-config.json").exists()

            # Verify JSON content
            with open(tmp_path / "mcp-config.json") as f:
                mcp_config = json.load(f)
                assert "mcpServers" in mcp_config
                assert "second-brain" in mcp_config["mcpServers"]
                server = mcp_config["mcpServers"]["second-brain"]
                assert server["command"] == "uv"
                assert server["args"] == ["run", "--", "mcp-second-brain"]
                assert server["env"]["PORT"] == "8080"
                assert server["env"]["OPENAI_API_KEY"] == "test-key"
                assert server["timeout"] == 3600000

    def test_show_command(self, tmp_path, monkeypatch):
        """Test show command."""
        monkeypatch.chdir(tmp_path)

        # Create config
        (tmp_path / "config.yaml").write_text("""
mcp:
  host: test-host
  port: 8888
providers:
  openai:
    api_key: secret-key
logging:
  level: DEBUG
""")

        with patch.dict(
            os.environ, {"MCP_CONFIG_FILE": str(tmp_path / "config.yaml")}, clear=True
        ):
            get_settings.cache_clear()
            # Show all config (default YAML format)
            result = runner.invoke(app, ["show"])
            assert result.exit_code == 0
            assert "host: test-host" in result.stdout
            assert "port: 8888" in result.stdout
            assert "api_key: ***" in result.stdout  # Masked

            # Show specific key
            result = runner.invoke(app, ["show", "mcp.port"])
            assert result.exit_code == 0
            assert "8888" in result.stdout

            # Show nested key
            result = runner.invoke(app, ["show", "openai.api_key"])
            assert result.exit_code == 0
            assert "***" in result.stdout  # Still masked

            # Show non-existent key
            result = runner.invoke(app, ["show", "invalid.key"])
            assert result.exit_code == 1
            assert "[ERROR] Key 'invalid.key' not found" in result.stdout

            # Different formats
            result = runner.invoke(app, ["show", "--format", "json"])
            assert result.exit_code == 0
            json_output = json.loads(result.stdout)
            assert json_output["mcp"]["port"] == 8888

            result = runner.invoke(app, ["show", "--format", "env"])
            assert result.exit_code == 0
            assert "PORT=8888" in result.stdout
            assert "HOST=test-host" in result.stdout

    def test_import_legacy_command(self, tmp_path, monkeypatch):
        """Test import-legacy command."""
        monkeypatch.chdir(tmp_path)

        # Create legacy .env file
        env_file = tmp_path / ".env"
        env_file.write_text("""
HOST=legacy-host
PORT=7777
OPENAI_API_KEY=legacy-key
VERTEX_PROJECT=legacy-project
VERTEX_LOCATION=us-west1
GCLOUD_OAUTH_CLIENT_ID=legacy-client-id
GCLOUD_OAUTH_CLIENT_SECRET=legacy-client-secret
GCLOUD_USER_REFRESH_TOKEN=legacy-refresh-token
LOG_LEVEL=WARNING
MEMORY_ENABLED=false
""")

        # Create legacy mcp-config.json
        mcp_config_file = tmp_path / "mcp-config.json"
        mcp_config_file.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "second-brain": {"env": {"ADDITIONAL_KEY": "from-mcp-config"}}
                    }
                }
            )
        )

        result = runner.invoke(app, ["import-legacy"])
        assert result.exit_code == 0
        assert "[OK] Successfully imported legacy configuration" in result.stdout

        # Check created files
        assert (tmp_path / "config.yaml").exists()
        assert (tmp_path / "secrets.yaml").exists()

        # Verify imported values
        with open(tmp_path / "config.yaml") as f:
            config = yaml.safe_load(f)
            assert config["mcp"]["host"] == "legacy-host"
            assert config["mcp"]["port"] == 7777
            assert config["logging"]["level"] == "WARNING"
            assert config["memory"]["enabled"] is False

        with open(tmp_path / "secrets.yaml") as f:
            secrets = yaml.safe_load(f)
            assert secrets["providers"]["openai"]["api_key"] == "legacy-key"
            assert (
                secrets["providers"]["vertex"]["oauth_client_id"] == "legacy-client-id"
            )
            assert (
                secrets["providers"]["vertex"]["oauth_client_secret"]
                == "legacy-client-secret"
            )
            assert (
                secrets["providers"]["vertex"]["user_refresh_token"]
                == "legacy-refresh-token"
            )

    def test_import_legacy_no_files(self, tmp_path, monkeypatch):
        """Test import-legacy with no legacy files."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["import-legacy"])
        assert result.exit_code == 1
        assert "[ERROR] No legacy configuration files found" in result.stdout

    def test_cli_error_handling(self, tmp_path, monkeypatch):
        """Test CLI error handling."""
        monkeypatch.chdir(tmp_path)

        # Test init with permission error
        with patch(
            "pathlib.Path.write_text", side_effect=PermissionError("No permission")
        ):
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 1
            assert "[ERROR] Permission denied" in result.stdout

        # Test export-env with write error
        (tmp_path / "config.yaml").write_text("mcp:\n  port: 8000")
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()

        with patch.dict(
            os.environ, {"MCP_CONFIG_FILE": str(tmp_path / "config.yaml")}, clear=True
        ):
            get_settings.cache_clear()
            with patch("pathlib.Path.write_text", side_effect=OSError("Write failed")):
                result = runner.invoke(app, ["export-env"])
                assert result.exit_code == 1
                assert "Failed to write" in result.stdout


class TestCLIHelpers:
    """Test CLI helper functions."""

    def test_mask_sensitive_values(self):
        """Test sensitive value masking."""
        from mcp_second_brain.cli.config_cli import _mask_sensitive

        # Test various sensitive keys
        data = {
            "api_key": "secret",
            "API_KEY": "SECRET",
            "password": "pass123",
            "secret": "mysecret",
            "token": "mytoken",
            "normal_key": "visible",
            "nested": {"api_key": "nested-secret", "safe": "visible"},
        }

        masked = _mask_sensitive(data)

        assert masked["api_key"] == "***"
        assert masked["API_KEY"] == "***"
        assert masked["password"] == "***"
        assert masked["secret"] == "***"
        assert masked["token"] == "***"
        assert masked["normal_key"] == "visible"
        assert masked["nested"]["api_key"] == "***"
        assert masked["nested"]["safe"] == "visible"

    def test_flatten_dict(self):
        """Test dictionary flattening for key access."""
        from mcp_second_brain.cli.config_cli import _flatten_dict

        nested = {
            "mcp": {"host": "localhost", "port": 8000},
            "providers": {"openai": {"api_key": "key", "enabled": True}},
        }

        flat = _flatten_dict(nested)

        assert flat["mcp.host"] == "localhost"
        assert flat["mcp.port"] == 8000
        assert flat["providers.openai.api_key"] == "key"
        assert flat["providers.openai.enabled"] is True

    def test_get_config_value(self):
        """Test getting specific config values."""
        from mcp_second_brain.cli.config_cli import _get_config_value

        config = {"mcp": {"port": 8000}, "providers": {"openai": {"api_key": "test"}}}

        # Test with clean environment (no overrides)
        with patch.dict(os.environ, {}, clear=True):
            assert _get_config_value(config, "mcp.port") == 8000
            assert _get_config_value(config, "providers.openai.api_key") == "test"
            assert _get_config_value(config, "invalid.key") is None
            assert _get_config_value(config, "mcp") == {"port": 8000}


class TestCLIIntegration:
    """Integration tests for CLI commands."""

    def test_full_workflow(self, tmp_path, monkeypatch):
        """Test complete workflow from init to export."""
        monkeypatch.chdir(tmp_path)

        # 1. Initialize configuration
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0

        # 2. Modify config files
        config_path = tmp_path / "config.yaml"
        config_content = config_path.read_text()
        config_content = config_content.replace("port: 8000", "port: 9999")
        config_path.write_text(config_content)

        secrets_path = tmp_path / "secrets.yaml"
        secrets_content = secrets_path.read_text()
        secrets_content = secrets_content.replace(
            'api_key: ""', 'api_key: "test-api-key"'
        )
        secrets_path.write_text(secrets_content)

        # 3. Validate configuration
        with patch.dict(
            os.environ,
            {
                "MCP_CONFIG_FILE": str(config_path),
                "MCP_SECRETS_FILE": str(secrets_path),
            },
            clear=True,
        ):
            get_settings.cache_clear()
            result = runner.invoke(app, ["validate"])
            assert result.exit_code == 0

            # 4. Export to .env
            get_settings.cache_clear()
            result = runner.invoke(app, ["export-env"])
            assert result.exit_code == 0
            env_content = (tmp_path / ".env").read_text()
            assert "PORT=9999" in env_content
            assert "OPENAI_API_KEY=test-api-key" in env_content

            # 5. Export to mcp-config.json
            get_settings.cache_clear()
            result = runner.invoke(app, ["export-client"])
            assert result.exit_code == 0
            with open(tmp_path / "mcp-config.json") as f:
                mcp_config = json.load(f)
                assert mcp_config["mcpServers"]["second-brain"]["env"]["PORT"] == "9999"

            # 6. Show configuration
            get_settings.cache_clear()
            result = runner.invoke(app, ["show", "mcp.port"])
            assert result.exit_code == 0
            assert "9999" in result.stdout

    def test_environment_override(self, tmp_path, monkeypatch):
        """Test that environment variables override config files in CLI."""
        monkeypatch.chdir(tmp_path)

        # Create config
        (tmp_path / "config.yaml").write_text("""
mcp:
  port: 8000
""")

        with patch.dict(
            os.environ,
            {
                "MCP_CONFIG_FILE": str(tmp_path / "config.yaml"),
                "PORT": "9999",  # Override via env
            },
            clear=True,
        ):
            result = runner.invoke(app, ["show", "mcp.port"])
            assert result.exit_code == 0
            assert "9999" in result.stdout  # Env var wins
