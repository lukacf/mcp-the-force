"""
Environment: Command building and environment isolation for CLI agents.

Provides HOME isolation and CLI-specific command construction.
"""

import os
from typing import Dict, List, Optional


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


class CommandBuilder:
    """
    Builds CLI-specific commands with appropriate flags.

    Handles differences in resume syntax:
    - Claude: --resume <session_id>
    - Gemini: --resume <session_id>
    - Codex: exec resume <thread_id>
    """

    def build_claude_command(
        self,
        task: str,
        role: str,
        resume_id: Optional[str],
        project_dir: str,
        context_dirs: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Build a Claude CLI command.

        Args:
            task: The task/prompt for Claude
            role: Role name for system prompt
            resume_id: CLI session ID to resume (optional)
            project_dir: Project directory
            context_dirs: Additional directories to add via --add-dir

        Returns:
            Command as list of strings
        """
        cmd = ["claude", "--print", "-p", task]

        if resume_id:
            cmd.extend(["--resume", resume_id])

        if context_dirs:
            for dir_path in context_dirs:
                cmd.extend(["--add-dir", dir_path])

        return cmd

    def build_gemini_command(
        self,
        task: str,
        resume_id: Optional[str],
        project_dir: str,
    ) -> List[str]:
        """
        Build a Gemini CLI command.

        Args:
            task: The task/prompt for Gemini
            resume_id: CLI session ID to resume (optional)
            project_dir: Project directory

        Returns:
            Command as list of strings
        """
        cmd = ["gemini", task]

        if resume_id:
            cmd.extend(["--resume", resume_id])

        return cmd

    def build_codex_command(
        self,
        task: str,
        resume_id: Optional[str],
        project_dir: str,
    ) -> List[str]:
        """
        Build a Codex CLI command.

        Note: Codex uses different resume syntax: exec resume <thread_id>

        Args:
            task: The task/prompt for Codex
            resume_id: Thread ID to resume (optional)
            project_dir: Project directory

        Returns:
            Command as list of strings
        """
        if resume_id:
            # Codex resume uses subcommand syntax
            return ["codex", "exec", "resume", resume_id]
        else:
            return ["codex", task]
