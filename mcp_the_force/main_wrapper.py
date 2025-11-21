"""Wrapper for uvx execution that handles configuration initialization."""

import os
import sys
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def ensure_config_exists():
    """Ensure configuration files exist, creating defaults if needed."""
    # If config files are already set via env vars, respect them
    if "MCP_CONFIG_FILE" in os.environ or "MCP_SECRETS_FILE" in os.environ:
        return

    # Safety check: Don't create config in home or root directories
    cwd = Path.cwd()
    if cwd == Path.home() or cwd == Path("/"):
        print(
            f"[MCP The-Force] ERROR: Cannot create configuration in {cwd}",
            file=sys.stderr,
        )
        print(
            "[MCP The-Force] Please run from a project directory, not from home or root",
            file=sys.stderr,
        )
        sys.exit(1)

    # Use current working directory as project root (MCP clients set this correctly)
    # Create .mcp-the-force directory to keep configs organized
    config_dir = cwd / ".mcp-the-force"

    try:
        config_dir.mkdir(exist_ok=True)
    except PermissionError as e:
        print(
            f"[MCP The-Force] ERROR: Cannot create config directory {config_dir}",
            file=sys.stderr,
        )
        print(f"[MCP The-Force] Permission denied: {e}", file=sys.stderr)
        print(f"[MCP The-Force] Please ensure write access to {cwd}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(
            f"[MCP The-Force] ERROR: Cannot create config directory {config_dir}",
            file=sys.stderr,
        )
        print(f"[MCP The-Force] Filesystem error: {e}", file=sys.stderr)
        print(
            f"[MCP The-Force] Check disk space and permissions for {cwd}",
            file=sys.stderr,
        )
        sys.exit(1)

    config_file = config_dir / "config.yaml"
    secrets_file = config_dir / "secrets.yaml"

    # Set environment variables so config.py can find them
    os.environ["MCP_CONFIG_FILE"] = str(config_file)
    os.environ["MCP_SECRETS_FILE"] = str(secrets_file)

    # Create default config.yaml if it doesn't exist
    if not config_file.exists():
        default_config = """# MCP The-Force Configuration
# Generated automatically on first run
# Edit this file to customize settings

mcp:
  host: 127.0.0.1
  port: 8000
  context_percentage: 0.85
  default_temperature: 1.0

logging:
  level: INFO

# Add provider configuration as needed
providers:
  openai:
    enabled: true
  vertex:
    enabled: true
  xai:
    enabled: true
"""
        config_file.write_text(default_config)
        print(
            f"[MCP The-Force] Created configuration at: {config_file}", file=sys.stderr
        )

    # Create secrets.yaml template if it doesn't exist
    if not secrets_file.exists():
        secrets_template = """# MCP The-Force Secrets
# Add your API keys here
# This file should be added to .gitignore

providers:
  openai:
    api_key: ""  # Add your OpenAI API key
  anthropic:
    api_key: ""  # Add your Anthropic API key
  xai:
    api_key: ""  # Add your xAI API key
  # vertex:
  #   # For CI/CD environments that can't use gcloud auth:
  #   oauth_client_id: ""
  #   oauth_client_secret: ""
  #   user_refresh_token: ""
"""
        secrets_file.write_text(secrets_template)
        secrets_file.chmod(0o600)  # Set secure permissions
        print(
            f"[MCP The-Force] Created secrets template at: {secrets_file}",
            file=sys.stderr,
        )
        print(
            f"[MCP The-Force] Please edit {secrets_file} to add your API keys",
            file=sys.stderr,
        )

        # Check if .gitignore exists and warn about adding .mcp-the-force
        gitignore = Path.cwd() / ".gitignore"
        if gitignore.exists():
            gitignore_content = gitignore.read_text()
            if ".mcp-the-force" not in gitignore_content:
                print(
                    "[MCP The-Force] WARNING: Add '.mcp-the-force/' to your .gitignore file to exclude sensitive data",
                    file=sys.stderr,
                )


def main():
    """Main entry point for uvx execution."""
    # Ensure configuration exists
    ensure_config_exists()

    # Import and run the actual server
    from .server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
