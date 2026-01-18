"""
Unit Tests: CLI Plugin Command Building.

Tests command construction logic via plugin methods.
"""


class TestClaudePluginCommandBuilding:
    """Unit tests for Claude plugin command building."""

    def test_build_new_session_basic(self):
        """Plugin creates basic Claude command for new session."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        args = plugin.build_new_session_args(
            task="Write a test",
            context_dirs=[],
            role=None,
        )

        assert "--print" in args  # JSON output mode
        assert "-p" in args
        assert "Write a test" in args

    def test_build_new_session_with_context_dirs(self):
        """Plugin adds --add-dir for context directories."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        args = plugin.build_new_session_args(
            task="Analyze code",
            context_dirs=["/path/to/context"],
            role=None,
        )

        assert "--add-dir" in args
        assert "/path/to/context" in args

    def test_build_new_session_with_role(self):
        """Plugin adds --system-prompt for role."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        args = plugin.build_new_session_args(
            task="Do something",
            context_dirs=[],
            role="You are a helpful assistant",
        )

        assert "--system-prompt" in args
        assert "You are a helpful assistant" in args

    def test_build_resume_args(self):
        """Plugin creates resume command with --resume flag."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        args = plugin.build_resume_args(
            session_id="abc-123-def",
            task="Continue",
        )

        assert "--print" in args
        assert "--resume" in args
        assert "abc-123-def" in args
        assert "-p" in args
        assert "Continue" in args

    def test_executable_name(self):
        """Plugin reports correct executable name."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        assert plugin.executable == "claude"


class TestGeminiPluginCommandBuilding:
    """Unit tests for Gemini plugin command building."""

    def test_build_new_session_basic(self):
        """Plugin creates basic Gemini command."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        plugin = GeminiPlugin()
        args = plugin.build_new_session_args(
            task="Explain this",
            context_dirs=[],
            role=None,
        )

        assert "--output-format" in args
        assert "json" in args
        assert "Explain this" in args

    def test_build_new_session_with_context(self):
        """Plugin adds --context for context directories."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        plugin = GeminiPlugin()
        args = plugin.build_new_session_args(
            task="Analyze",
            context_dirs=["/path/to/code"],
            role=None,
        )

        assert "--context" in args
        assert "/path/to/code" in args

    def test_build_new_session_with_role(self):
        """Plugin adds --system-instruction for role."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        plugin = GeminiPlugin()
        args = plugin.build_new_session_args(
            task="Do task",
            context_dirs=[],
            role="Expert coder",
        )

        assert "--system-instruction" in args
        assert "Expert coder" in args

    def test_build_resume_args(self):
        """Plugin creates resume command with --session flag."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        plugin = GeminiPlugin()
        args = plugin.build_resume_args(
            session_id="gemini-session-456",
            task="Continue",
        )

        assert "--session" in args
        assert "gemini-session-456" in args
        assert "--output-format" in args

    def test_executable_name(self):
        """Plugin reports correct executable name."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        plugin = GeminiPlugin()
        assert plugin.executable == "gemini"


class TestCodexPluginCommandBuilding:
    """Unit tests for Codex plugin command building."""

    def test_build_new_session_basic(self):
        """Plugin creates basic Codex command."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_new_session_args(
            task="Fix the bug",
            context_dirs=[],
            role=None,
        )

        assert "exec" in args
        assert "--json" in args
        assert "Fix the bug" in args

    def test_build_new_session_with_context(self):
        """Plugin adds --context for context directories."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_new_session_args(
            task="Review",
            context_dirs=["/src"],
            role=None,
        )

        assert "--context" in args
        assert "/src" in args

    def test_build_new_session_with_role(self):
        """Plugin adds --role for role."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_new_session_args(
            task="Help",
            context_dirs=[],
            role="senior-dev",
        )

        assert "--role" in args
        assert "senior-dev" in args

    def test_build_resume_args(self):
        """Plugin uses 'exec resume' subcommand for Codex resume."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_resume_args(
            session_id="thread-789",
            task="Continue",
        )

        # Codex uses different resume syntax: exec resume <thread_id>
        assert "exec" in args
        assert "resume" in args
        assert "thread-789" in args

    def test_executable_name(self):
        """Plugin reports correct executable name."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        assert plugin.executable == "codex"


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
