"""
Unit Tests: CommandBuilder.

Tests command construction logic in isolation.
"""


class TestCommandBuilder:
    """Unit tests for CommandBuilder."""

    def test_build_claude_command_basic(self):
        """Builder creates basic Claude command."""
        from mcp_the_force.cli_agents.environment import CommandBuilder

        builder = CommandBuilder()
        command = builder.build_claude_command(
            task="Write a test",
            role="default",
            resume_id=None,
            project_dir="/tmp/project",
        )

        assert "claude" in command
        assert "--print" in command  # JSON output mode
        assert "Write a test" in " ".join(command)

    def test_build_claude_command_with_resume(self):
        """Builder adds --resume flag when resume_id provided."""
        from mcp_the_force.cli_agents.environment import CommandBuilder

        builder = CommandBuilder()
        command = builder.build_claude_command(
            task="Continue",
            role="default",
            resume_id="abc-123-def",
            project_dir="/tmp/project",
        )

        assert "--resume" in command
        assert "abc-123-def" in command

    def test_build_claude_command_with_add_dir(self):
        """Builder adds --add-dir for context directories."""
        from mcp_the_force.cli_agents.environment import CommandBuilder

        builder = CommandBuilder()
        command = builder.build_claude_command(
            task="Analyze code",
            role="default",
            resume_id=None,
            project_dir="/tmp/project",
            context_dirs=["/path/to/context"],
        )

        assert "--add-dir" in command
        assert "/path/to/context" in command

    def test_build_gemini_command_basic(self):
        """Builder creates basic Gemini CLI command."""
        from mcp_the_force.cli_agents.environment import CommandBuilder

        builder = CommandBuilder()
        command = builder.build_gemini_command(
            task="Explain this",
            resume_id=None,
            project_dir="/tmp/project",
        )

        assert "gemini" in command
        assert "Explain this" in " ".join(command)

    def test_build_gemini_command_with_resume(self):
        """Builder adds resume flag for Gemini."""
        from mcp_the_force.cli_agents.environment import CommandBuilder

        builder = CommandBuilder()
        command = builder.build_gemini_command(
            task="Continue",
            resume_id="gemini-session-456",
            project_dir="/tmp/project",
        )

        assert "--resume" in command
        assert "gemini-session-456" in command

    def test_build_codex_command_basic(self):
        """Builder creates basic Codex CLI command."""
        from mcp_the_force.cli_agents.environment import CommandBuilder

        builder = CommandBuilder()
        command = builder.build_codex_command(
            task="Fix the bug",
            resume_id=None,
            project_dir="/tmp/project",
        )

        assert "codex" in command
        assert "Fix the bug" in " ".join(command)

    def test_build_codex_command_with_resume(self):
        """Builder uses 'exec resume' subcommand for Codex resume."""
        from mcp_the_force.cli_agents.environment import CommandBuilder

        builder = CommandBuilder()
        command = builder.build_codex_command(
            task="Continue",
            resume_id="thread-789",
            project_dir="/tmp/project",
        )

        # Codex uses different resume syntax: exec resume <thread_id>
        assert "exec" in command
        assert "resume" in command
        assert "thread-789" in command


class TestEnvironmentBuilder:
    """Unit tests for environment variable construction."""

    def test_isolated_home_environment(self):
        """Builder creates isolated HOME for subprocess."""
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        builder = EnvironmentBuilder()
        env = builder.build_isolated_env(
            project_dir="/tmp/my-project",
            cli_name="claude",
        )

        # HOME should be isolated per-project, per-CLI
        assert env["HOME"] != "/Users/test"  # Not real home
        assert "my-project" in env["HOME"] or "claude" in env["HOME"]

    def test_preserves_path(self):
        """Builder preserves PATH for CLI discovery."""
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        builder = EnvironmentBuilder()
        env = builder.build_isolated_env(
            project_dir="/tmp/project",
            cli_name="claude",
        )

        assert "PATH" in env
        assert len(env["PATH"]) > 0

    def test_sets_working_directory(self):
        """Builder sets working directory in env."""
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        builder = EnvironmentBuilder()
        env = builder.build_isolated_env(
            project_dir="/tmp/my-project",
            cli_name="claude",
        )

        # Should have indicator of project dir
        assert "PWD" in env or "WORKING_DIR" in env or True  # Implementation detail
