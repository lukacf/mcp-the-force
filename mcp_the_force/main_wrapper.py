"""Wrapper for uvx execution that handles configuration initialization."""

import os
import sys
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def get_config_dir() -> Path:
    """Get configuration directory following XDG Base Directory specification."""
    # Use XDG_CONFIG_HOME if set, otherwise ~/.config
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        config_dir = Path(xdg_config_home) / "mcp-the-force"
    else:
        config_dir = Path.home() / ".config" / "mcp-the-force"

    # Create directory if it doesn't exist
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def ensure_config_exists():
    """Ensure configuration files exist, creating defaults if needed."""
    config_dir = get_config_dir()
    config_file = config_dir / "config.yaml"
    secrets_file = config_dir / "secrets.yaml"

    # Set environment variables to point to our config location
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
        print(f"Created default configuration at: {config_file}", file=sys.stderr)

    # Create secrets.yaml template if it doesn't exist
    if not secrets_file.exists():
        secrets_template = """# MCP The-Force Secrets
# Add your API keys here
# This file is automatically excluded from git

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
        print(f"Created secrets template at: {secrets_file}", file=sys.stderr)
        print(f"Please edit {secrets_file} to add your API keys", file=sys.stderr)


def main():
    """Main entry point for uvx execution."""
    # Ensure configuration exists
    ensure_config_exists()

    # Import and run the actual server
    from .server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
