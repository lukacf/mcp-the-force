"""
Environment: Environment isolation for CLI agents.

Provides HOME isolation for subprocess execution.
Command building is handled by CLI plugins in cli_plugins/*.
"""

import logging
import os
from pathlib import Path
from typing import Dict

from mcp_the_force.config import get_settings

logger = logging.getLogger(__name__)


class EnvironmentBuilder:
    """
    Builds isolated environment variables for CLI subprocess execution.

    Ensures each project+CLI combination gets a separate HOME directory
    to prevent session/config conflicts. Also injects API keys from
    MCP The Force config into the subprocess environment.
    """

    # Map CLI names to the environment variables they need
    CLI_API_KEY_MAPPING = {
        "claude": [("ANTHROPIC_API_KEY", lambda s: s.anthropic.api_key)],
        # Codex CLI uses CODEX_API_KEY for non-interactive exec mode
        # See: https://developers.openai.com/codex/noninteractive/
        "codex": [("CODEX_API_KEY", lambda s: s.openai.api_key)],
        "gemini": [
            ("GEMINI_API_KEY", lambda s: s.gemini.api_key),
        ],
    }

    # Map CLI names to the config directories they need symlinked from real HOME
    # These directories contain auth tokens that can't be injected via env vars
    CLI_CONFIG_DIRS = {
        "codex": [".codex"],  # Codex uses OAuth tokens in ~/.codex/auth.json
        "claude": [".claude"],  # Claude may use config in ~/.claude/
        "gemini": [".gemini"],  # Gemini may use config in ~/.gemini/
    }

    def build_isolated_env(
        self,
        project_dir: str,
        cli_name: str,
    ) -> Dict[str, str]:
        """
        Build environment variables with isolated HOME and injected API keys.

        Args:
            project_dir: Project directory path
            cli_name: CLI name (claude, gemini, codex)

        Returns:
            Environment dict with isolated HOME, preserved PATH, and API keys
        """
        # Get base environment
        env = os.environ.copy()

        # Debug: log if GEMINI_API_KEY is in the process env
        if cli_name == "gemini":
            has_key = "GEMINI_API_KEY" in os.environ
            key_preview = (
                os.environ.get("GEMINI_API_KEY", "")[:10] if has_key else "NOT SET"
            )
            logger.info(
                f"[ENV-DEBUG] GEMINI_API_KEY in os.environ: {has_key}, preview: {key_preview}..."
            )

        # Create isolated HOME based on project and CLI
        # This prevents CLI configs from conflicting
        project_hash = abs(hash(project_dir)) % 10000
        isolated_home = f"/tmp/.mcp-the-force/{project_hash}/{cli_name}"

        # Create the isolated HOME directory if it doesn't exist
        Path(isolated_home).mkdir(parents=True, exist_ok=True)

        env["HOME"] = isolated_home
        env["PWD"] = project_dir

        # Symlink CLI config directories from real HOME (for OAuth tokens, etc.)
        self._symlink_config_dirs(isolated_home, cli_name)

        # Inject API keys from MCP The Force config
        self._inject_api_keys(env, cli_name)

        return env

    def _symlink_config_dirs(self, isolated_home: str, cli_name: str) -> None:
        """
        Symlink CLI config directories from real HOME into isolated HOME.

        Some CLIs (like Codex) use OAuth tokens stored in config files
        that can't be injected via environment variables.

        Args:
            isolated_home: The isolated HOME directory
            cli_name: CLI name (claude, gemini, codex)
        """
        real_home = os.environ.get("HOME", "")
        if not real_home:
            return

        config_dirs = self.CLI_CONFIG_DIRS.get(cli_name, [])

        for config_dir in config_dirs:
            source = Path(real_home) / config_dir
            target = Path(isolated_home) / config_dir

            if source.exists() and not target.exists():
                try:
                    # Create symlink from isolated HOME to real config dir
                    target.symlink_to(source)
                    logger.debug(f"Symlinked {config_dir} for {cli_name} CLI")
                except Exception as e:
                    logger.debug(f"Could not symlink {config_dir} for {cli_name}: {e}")

    def _inject_api_keys(self, env: Dict[str, str], cli_name: str) -> None:
        """
        Inject API keys for the specified CLI from MCP The Force config.

        Args:
            env: Environment dict to modify
            cli_name: CLI name (claude, gemini, codex)
        """
        try:
            settings = get_settings()

            # Get the API key mappings for this CLI
            mappings = self.CLI_API_KEY_MAPPING.get(cli_name, [])
            injected = []
            missing = []

            for env_var, getter in mappings:
                try:
                    value = getter(settings)
                    logger.info(
                        f"[ENV-DEBUG] {env_var}: settings value is {'SET' if value else 'EMPTY/NONE'}"
                    )
                    if value:
                        env[env_var] = value
                        # Don't log actual key values
                        injected.append(env_var)
                    else:
                        # Check if it's in os.environ (from shell)
                        if env_var in env:
                            logger.debug(
                                f"{env_var} not in config but found in process env"
                            )
                        else:
                            missing.append(env_var)
                except Exception as e:
                    logger.warning(
                        f"[ENV-DEBUG] Could not get {env_var} for {cli_name}: {e}"
                    )
                    missing.append(env_var)

            if injected:
                logger.info(f"[ENV] Injected for {cli_name}: {', '.join(injected)}")
            if missing:
                logger.warning(
                    f"[ENV] Missing for {cli_name}: {', '.join(missing)} (not in config or env)"
                )

        except Exception as e:
            logger.warning(f"Could not inject API keys for {cli_name}: {e}")
