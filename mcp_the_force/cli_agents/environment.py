"""
Environment: Environment isolation for CLI agents.

Provides HOME isolation for subprocess execution.
Command building is handled by CLI plugins in cli_plugins/*.
"""

import os
from typing import Dict


class EnvironmentBuilder:
    """
    Builds isolated environment variables for CLI subprocess execution.

    Ensures each project+CLI combination gets a separate HOME directory
    to prevent session/config conflicts.
    """

    def build_isolated_env(
        self,
        project_dir: str,
        cli_name: str,
    ) -> Dict[str, str]:
        """
        Build environment variables with isolated HOME.

        Args:
            project_dir: Project directory path
            cli_name: CLI name (claude, gemini, codex)

        Returns:
            Environment dict with isolated HOME and preserved PATH
        """
        # Get base environment
        env = os.environ.copy()

        # Create isolated HOME based on project and CLI
        # This prevents CLI configs from conflicting
        project_hash = abs(hash(project_dir)) % 10000
        isolated_home = f"/tmp/.mcp-the-force/{project_hash}/{cli_name}"

        env["HOME"] = isolated_home
        env["PWD"] = project_dir

        return env
