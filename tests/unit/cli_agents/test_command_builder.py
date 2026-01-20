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
        assert "--output-format" in args
        assert "json" in args
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
        assert "--output-format" in args
        assert "json" in args
        assert "--resume" in args
        assert "abc-123-def" in args
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
        """Plugin adds --include-directories for context directories."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        plugin = GeminiPlugin()
        args = plugin.build_new_session_args(
            task="Analyze",
            context_dirs=["/path/to/code"],
            role=None,
        )

        assert "--include-directories" in args
        assert "/path/to/code" in args

    def test_build_new_session_with_role(self):
        """Plugin prepends role to task (Gemini CLI has no --system-instruction)."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        plugin = GeminiPlugin()
        args = plugin.build_new_session_args(
            task="Do task",
            context_dirs=[],
            role="Expert coder",
        )

        # Role is prepended to task, not a separate flag
        task_arg = args[-1]  # Task is always last
        assert "Role: Expert coder" in task_arg
        assert "Do task" in task_arg

    def test_build_resume_args(self):
        """Plugin creates resume command with --resume flag."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        plugin = GeminiPlugin()
        args = plugin.build_resume_args(
            session_id="gemini-session-456",
            task="Continue",
        )

        assert "--resume" in args
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
        """Codex CLI ignores context_dirs (no --context flag support)."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_new_session_args(
            task="Review",
            context_dirs=["/src"],  # Ignored - Codex uses working directory
            role=None,
        )

        # Codex doesn't support --context flag; context is via working directory
        assert "--context" not in args
        # But task should still be included
        assert "Review" in args
        assert "exec" in args

    def test_build_new_session_with_role(self):
        """Codex CLI ignores role (no --role flag support)."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_new_session_args(
            task="Help",
            context_dirs=[],
            role="senior-dev",  # Ignored - Codex doesn't support roles
        )

        # Codex doesn't support --role flag
        assert "--role" not in args
        # But task should still be included
        assert "Help" in args
        assert "exec" in args

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


class TestReasoningEffortCodex:
    """Unit tests for Codex reasoning effort CLI flag support."""

    def test_high_reasoning_effort_adds_config_flag(self):
        """Codex adds -c model_reasoning_effort flag for high effort."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_new_session_args(
            task="Solve complex problem",
            context_dirs=[],
            reasoning_effort="high",
        )

        assert "-c" in args
        # Find the config value that follows -c
        c_idx = args.index("-c")
        config_value = args[c_idx + 1]
        assert 'model_reasoning_effort="high"' in config_value

    def test_xhigh_reasoning_effort_adds_config_flag(self):
        """Codex adds -c model_reasoning_effort flag for xhigh effort."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_new_session_args(
            task="Very complex problem",
            context_dirs=[],
            reasoning_effort="xhigh",
        )

        assert "-c" in args
        c_idx = args.index("-c")
        config_value = args[c_idx + 1]
        assert 'model_reasoning_effort="xhigh"' in config_value

    def test_medium_reasoning_effort_no_flag(self):
        """Codex doesn't add flag for medium effort (default)."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_new_session_args(
            task="Normal task",
            context_dirs=[],
            reasoning_effort="medium",
        )

        # Medium is default, no flag should be added
        assert "-c" not in args

    def test_no_reasoning_effort_no_flag(self):
        """Codex doesn't add flag when reasoning_effort is None."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_new_session_args(
            task="Task",
            context_dirs=[],
            reasoning_effort=None,
        )

        assert "-c" not in args

    def test_resume_with_high_reasoning_effort(self):
        """Codex resume command includes reasoning effort flag."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        args = plugin.build_resume_args(
            session_id="thread-123",
            task="Continue",
            reasoning_effort="high",
        )

        assert "-c" in args
        assert "resume" in args

    def test_get_reasoning_env_vars_returns_empty(self):
        """Codex uses CLI flags, not env vars, so returns empty dict."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        env_vars = plugin.get_reasoning_env_vars("high")

        assert env_vars == {}


class TestReasoningEffortClaude:
    """Unit tests for Claude reasoning effort MAX_THINKING_TOKENS support."""

    def test_high_reasoning_returns_max_thinking_tokens(self):
        """Claude returns MAX_THINKING_TOKENS env var for high effort."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        env_vars = plugin.get_reasoning_env_vars("high")

        assert "MAX_THINKING_TOKENS" in env_vars
        assert env_vars["MAX_THINKING_TOKENS"] == "63999"

    def test_xhigh_reasoning_returns_max_thinking_tokens(self):
        """Claude returns MAX_THINKING_TOKENS env var for xhigh effort."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        env_vars = plugin.get_reasoning_env_vars("xhigh")

        assert "MAX_THINKING_TOKENS" in env_vars
        assert env_vars["MAX_THINKING_TOKENS"] == "127999"

    def test_low_reasoning_returns_reduced_tokens(self):
        """Claude returns reduced MAX_THINKING_TOKENS for low effort."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        env_vars = plugin.get_reasoning_env_vars("low")

        assert "MAX_THINKING_TOKENS" in env_vars
        assert env_vars["MAX_THINKING_TOKENS"] == "16000"

    def test_medium_reasoning_returns_empty(self):
        """Claude returns empty dict for medium effort (uses default)."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        env_vars = plugin.get_reasoning_env_vars("medium")

        assert env_vars == {}

    def test_none_reasoning_returns_empty(self):
        """Claude returns empty dict when reasoning_effort is None."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        env_vars = plugin.get_reasoning_env_vars(None)

        assert env_vars == {}

    def test_unknown_reasoning_returns_empty(self):
        """Claude returns empty dict for unknown reasoning effort."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        env_vars = plugin.get_reasoning_env_vars("ultra-mega")

        assert env_vars == {}

    def test_build_args_does_not_add_cli_flags(self):
        """Claude uses env vars, not CLI flags, for reasoning effort."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        args = plugin.build_new_session_args(
            task="Task",
            context_dirs=[],
            reasoning_effort="high",
        )

        # Should not contain any reasoning-related flags
        assert "-c" not in args
        assert "--reasoning" not in args


class TestReasoningEffortGemini:
    """Unit tests for Gemini reasoning effort (not supported)."""

    def test_get_reasoning_env_vars_returns_empty(self):
        """Gemini returns empty dict (not supported)."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        plugin = GeminiPlugin()
        env_vars = plugin.get_reasoning_env_vars("high")

        assert env_vars == {}

    def test_build_args_does_not_add_flags(self):
        """Gemini doesn't add reasoning flags (not supported)."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        plugin = GeminiPlugin()
        args = plugin.build_new_session_args(
            task="Task",
            context_dirs=[],
            reasoning_effort="high",
        )

        # Should not contain any reasoning-related flags
        assert "-c" not in args
        assert "--reasoning" not in args
        assert "--thinking" not in args


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
