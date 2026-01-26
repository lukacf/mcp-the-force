"""
Unit Tests: Environment Isolation (REQ-5.1.2).

Tests for HOME directory isolation and environment variable management.
"""

import pytest
import os


class TestHomeIsolation:
    """Unit tests for HOME directory isolation."""

    def test_home_redirect_creates_isolated_path(self):
        """
        REQ-5.1.2: HOME is redirected for session isolation.

        Given: A CLI execution request
        When: Environment is built
        Then: HOME is redirected to an isolated directory
        """
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        builder = EnvironmentBuilder()
        env = builder.build_isolated_env(
            project_dir="/tmp/my-project",
            cli_name="claude",
        )

        # HOME should NOT be the user's actual home
        actual_home = os.environ.get("HOME", "")
        assert env["HOME"] != actual_home
        assert "/tmp" in env["HOME"] or ".mcp-the-force" in env["HOME"]

    def test_home_isolation_per_project(self):
        """
        HOME isolation is per-project.

        Given: Two different project directories
        When: Environment is built for each
        Then: Each gets a different isolated HOME
        """
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        builder = EnvironmentBuilder()

        env1 = builder.build_isolated_env(
            project_dir="/tmp/project-a",
            cli_name="claude",
        )
        env2 = builder.build_isolated_env(
            project_dir="/tmp/project-b",
            cli_name="claude",
        )

        assert env1["HOME"] != env2["HOME"]

    def test_home_isolation_per_cli(self):
        """
        HOME isolation is per-CLI within same project.

        Given: Same project, different CLIs
        When: Environment is built for each CLI
        Then: Each CLI gets different isolated HOME
        """
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        builder = EnvironmentBuilder()

        env_claude = builder.build_isolated_env(
            project_dir="/tmp/project",
            cli_name="claude",
        )
        env_gemini = builder.build_isolated_env(
            project_dir="/tmp/project",
            cli_name="gemini",
        )
        env_codex = builder.build_isolated_env(
            project_dir="/tmp/project",
            cli_name="codex",
        )

        homes = [env_claude["HOME"], env_gemini["HOME"], env_codex["HOME"]]
        assert len(set(homes)) == 3  # All different

    def test_home_path_deterministic(self):
        """
        HOME path is deterministic for same inputs.

        Given: Same project and CLI name
        When: Environment is built multiple times
        Then: Same HOME path is returned (deterministic)
        """
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        builder = EnvironmentBuilder()

        env1 = builder.build_isolated_env(
            project_dir="/tmp/project",
            cli_name="claude",
        )
        env2 = builder.build_isolated_env(
            project_dir="/tmp/project",
            cli_name="claude",
        )

        assert env1["HOME"] == env2["HOME"]


class TestPathPreservation:
    """Unit tests for PATH environment variable handling."""

    def test_path_preserved_in_environment(self):
        """
        PATH is preserved for CLI discovery.

        Given: Environment is built
        When: PATH is checked
        Then: PATH contains necessary directories for CLI execution
        """
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        builder = EnvironmentBuilder()
        env = builder.build_isolated_env(
            project_dir="/tmp/project",
            cli_name="claude",
        )

        assert "PATH" in env
        assert "/usr/bin" in env["PATH"] or "/bin" in env["PATH"]

    def test_path_includes_homebrew_if_present(self):
        """
        PATH includes Homebrew paths if on macOS.

        Given: Environment is built on macOS
        When: PATH is checked
        Then: Homebrew paths are included (if present in system)
        """
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder
        import sys

        if sys.platform != "darwin":
            pytest.skip("Homebrew test only relevant on macOS")

        builder = EnvironmentBuilder()
        env = builder.build_isolated_env(
            project_dir="/tmp/project",
            cli_name="claude",
        )

        # Should include homebrew if it exists in system PATH
        system_path = os.environ.get("PATH", "")
        if "/opt/homebrew" in system_path:
            assert "/opt/homebrew" in env["PATH"]


class TestWorkingDirectory:
    """Unit tests for working directory configuration."""

    def test_working_directory_set(self):
        """
        Working directory is configured in environment.

        Given: A project directory
        When: Environment is built
        Then: Working directory indicators are set
        """
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        builder = EnvironmentBuilder()
        env = builder.build_isolated_env(
            project_dir="/tmp/my-project",
            cli_name="claude",
        )

        # Should have some indicator of project dir
        assert "PWD" in env or env.get("PROJECT_DIR") == "/tmp/my-project"

    def test_xdg_config_home_isolated(self):
        """
        XDG_CONFIG_HOME is isolated to prevent config conflicts.

        Given: Environment is built
        When: XDG_CONFIG_HOME is checked
        Then: It points to isolated location (not user's config)
        """
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        builder = EnvironmentBuilder()
        env = builder.build_isolated_env(
            project_dir="/tmp/project",
            cli_name="claude",
        )

        if "XDG_CONFIG_HOME" in env:
            actual_config = os.environ.get("XDG_CONFIG_HOME", "")
            assert env["XDG_CONFIG_HOME"] != actual_config
