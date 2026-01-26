"""
Unit Tests: Transcript Locator for CLI Plugins.

Tests the locate_transcript() method for each CLI plugin.
This enables live_follow_session functionality.
"""

from unittest.mock import patch


class TestCodexTranscriptLocator:
    """Tests for Codex CLI transcript location."""

    def test_locate_transcript_finds_file_by_thread_id(self, tmp_path):
        """Codex plugin finds transcript by thread_id in JSONL files."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        # Create mock Codex session directory structure
        sessions_dir = tmp_path / ".codex" / "sessions" / "2026" / "01" / "21"
        sessions_dir.mkdir(parents=True)

        # Create a transcript file with the thread_id we're looking for
        transcript_file = sessions_dir / "rollout-2026-01-21T10-00-00-abc123.jsonl"
        transcript_file.write_text(
            '{"type": "thread.started", "thread_id": "thread-xyz-789"}\n'
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "Hello"}}\n'
        )

        # Create another transcript file (decoy)
        decoy_file = sessions_dir / "rollout-2026-01-21T09-00-00-def456.jsonl"
        decoy_file.write_text(
            '{"type": "thread.started", "thread_id": "thread-other-000"}\n'
        )

        plugin = CodexPlugin()
        with patch.dict("os.environ", {"HOME": str(tmp_path)}):
            result = plugin.locate_transcript(
                cli_session_id="thread-xyz-789",
                project_dir="/some/project",
            )

        assert result is not None
        assert result == transcript_file

    def test_locate_transcript_finds_file_by_session_meta_format(self, tmp_path):
        """Regression: Codex plugin finds transcript with session_meta format."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        # Create mock Codex session directory structure
        sessions_dir = tmp_path / ".codex" / "sessions" / "2026" / "01" / "21"
        sessions_dir.mkdir(parents=True)

        # Create transcript with session_meta format (current Codex format)
        transcript_file = sessions_dir / "rollout-2026-01-21T10-40-55-019bdfed.jsonl"
        transcript_file.write_text(
            '{"type": "session_meta", "payload": {"id": "019bdfed-b319-77f2-86d1-ad4bc4a7992b"}}\n'
            '{"type": "response_item", "payload": {"type": "message"}}\n'
        )

        plugin = CodexPlugin()
        with patch.dict("os.environ", {"HOME": str(tmp_path)}):
            result = plugin.locate_transcript(
                cli_session_id="019bdfed-b319-77f2-86d1-ad4bc4a7992b",
                project_dir="/some/project",
            )

        assert result is not None
        assert result == transcript_file

    def test_locate_transcript_returns_none_when_not_found(self, tmp_path):
        """Codex plugin returns None when thread_id not found."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        # Create empty sessions directory
        sessions_dir = tmp_path / ".codex" / "sessions" / "2026" / "01" / "21"
        sessions_dir.mkdir(parents=True)

        plugin = CodexPlugin()
        with patch.dict("os.environ", {"HOME": str(tmp_path)}):
            result = plugin.locate_transcript(
                cli_session_id="thread-nonexistent",
                project_dir="/some/project",
            )

        assert result is None

    def test_locate_transcript_searches_recent_days(self, tmp_path):
        """Codex plugin searches multiple recent days for transcripts."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        # Create session in "yesterday's" directory
        yesterday_dir = tmp_path / ".codex" / "sessions" / "2026" / "01" / "20"
        yesterday_dir.mkdir(parents=True)

        transcript_file = yesterday_dir / "rollout-2026-01-20T23-00-00-old123.jsonl"
        transcript_file.write_text(
            '{"type": "thread.started", "thread_id": "thread-from-yesterday"}\n'
        )

        plugin = CodexPlugin()
        with patch.dict("os.environ", {"HOME": str(tmp_path)}):
            result = plugin.locate_transcript(
                cli_session_id="thread-from-yesterday",
                project_dir="/some/project",
            )

        assert result is not None
        assert result == transcript_file


class TestClaudeTranscriptLocator:
    """Tests for Claude Code CLI transcript location."""

    def test_locate_transcript_finds_file_by_session_id(self, tmp_path):
        """Claude plugin finds transcript by session ID in project folder."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        # Claude uses path-based hashing for project folders
        # e.g., /Users/luka/src/raik -> -Users-luka-src-raik
        project_dir = "/Users/test/myproject"
        project_hash = "-Users-test-myproject"

        # Create mock Claude projects directory
        projects_dir = tmp_path / ".claude" / "projects" / project_hash
        projects_dir.mkdir(parents=True)

        # Create transcript file
        transcript_file = projects_dir / "session-abc-123.jsonl"
        transcript_file.write_text(
            '{"type": "user", "message": "Hello"}\n'
            '{"type": "assistant", "message": "Hi there"}\n'
        )

        plugin = ClaudePlugin()
        with patch.dict("os.environ", {"HOME": str(tmp_path)}):
            result = plugin.locate_transcript(
                cli_session_id="session-abc-123",
                project_dir=project_dir,
            )

        assert result is not None
        assert result == transcript_file

    def test_locate_transcript_finds_agent_transcript(self, tmp_path):
        """Claude plugin finds agent-{id}.jsonl transcripts."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        project_dir = "/Users/test/myproject"
        project_hash = "-Users-test-myproject"

        projects_dir = tmp_path / ".claude" / "projects" / project_hash
        projects_dir.mkdir(parents=True)

        # Agent transcripts use agent-{agentId}.jsonl format
        transcript_file = projects_dir / "agent-xyz-456.jsonl"
        transcript_file.write_text('{"type": "agent_start"}\n')

        plugin = ClaudePlugin()
        with patch.dict("os.environ", {"HOME": str(tmp_path)}):
            result = plugin.locate_transcript(
                cli_session_id="agent-xyz-456",
                project_dir=project_dir,
            )

        assert result is not None
        assert result == transcript_file

    def test_locate_transcript_computes_project_hash(self, tmp_path):
        """Claude plugin correctly computes project path hash."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()

        # Test hash computation
        assert (
            plugin._compute_project_hash("/Users/luka/src/raik")
            == "-Users-luka-src-raik"
        )
        assert (
            plugin._compute_project_hash("/home/user/project") == "-home-user-project"
        )

    def test_locate_transcript_returns_none_when_project_not_found(self, tmp_path):
        """Claude plugin returns None when project folder doesn't exist."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        with patch.dict("os.environ", {"HOME": str(tmp_path)}):
            result = plugin.locate_transcript(
                cli_session_id="any-session",
                project_dir="/nonexistent/project",
            )

        assert result is None


class TestGeminiTranscriptLocator:
    """Tests for Gemini CLI transcript location."""

    def test_locate_transcript_finds_latest_chat(self, tmp_path):
        """Gemini plugin finds latest chat file in project's chats folder."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        # Gemini uses SHA256 hash of project path
        project_dir = "/Users/test/myproject"

        # Create mock Gemini tmp directory with hashed project folder
        # We'll mock the hash computation
        project_hash = "abc123hash"
        gemini_dir = tmp_path / ".gemini" / "tmp" / project_hash / "chats"
        gemini_dir.mkdir(parents=True)

        # Create chat files with timestamps
        older_chat = gemini_dir / "chat-2026-01-21T09-00-00.json"
        older_chat.write_text('{"messages": []}')

        newer_chat = gemini_dir / "chat-2026-01-21T10-00-00.json"
        newer_chat.write_text('{"messages": [{"role": "user", "content": "test"}]}')

        plugin = GeminiPlugin()
        with (
            patch.dict("os.environ", {"HOME": str(tmp_path)}),
            patch.object(plugin, "_compute_project_hash", return_value=project_hash),
        ):
            result = plugin.locate_transcript(
                cli_session_id=None,  # Gemini uses latest by default
                project_dir=project_dir,
            )

        assert result is not None
        # Should return the newer chat
        assert "10-00-00" in str(result)

    def test_locate_transcript_finds_by_session_tag(self, tmp_path):
        """Gemini plugin finds chat saved with specific tag."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        project_dir = "/Users/test/myproject"
        project_hash = "abc123hash"

        gemini_dir = tmp_path / ".gemini" / "tmp" / project_hash
        gemini_dir.mkdir(parents=True)

        # Gemini saves tagged sessions as checkpoint-tag-{tag}.json
        tagged_chat = gemini_dir / "checkpoint-tag-my-task.json"
        tagged_chat.write_text('{"messages": []}')

        plugin = GeminiPlugin()
        with (
            patch.dict("os.environ", {"HOME": str(tmp_path)}),
            patch.object(plugin, "_compute_project_hash", return_value=project_hash),
        ):
            result = plugin.locate_transcript(
                cli_session_id="my-task",  # Tag name
                project_dir=project_dir,
            )

        assert result is not None
        assert "checkpoint-tag-my-task" in str(result)

    def test_locate_transcript_returns_none_when_no_chats(self, tmp_path):
        """Gemini plugin returns None when no chat files exist."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        project_hash = "abc123hash"
        gemini_dir = tmp_path / ".gemini" / "tmp" / project_hash
        gemini_dir.mkdir(parents=True)
        # No chats directory or files

        plugin = GeminiPlugin()
        with (
            patch.dict("os.environ", {"HOME": str(tmp_path)}),
            patch.object(plugin, "_compute_project_hash", return_value=project_hash),
        ):
            result = plugin.locate_transcript(
                cli_session_id=None,
                project_dir="/Users/test/myproject",
            )

        assert result is None


class TestBasePluginTranscriptInterface:
    """Tests for base plugin transcript interface."""

    def test_base_plugin_has_locate_transcript_method(self):
        """Base plugin defines locate_transcript interface."""
        from mcp_the_force.cli_plugins.base import CLIPluginBase

        # Should have the method defined (can be abstract or default impl)
        assert hasattr(CLIPluginBase, "locate_transcript")

    def test_base_plugin_default_returns_none(self):
        """Base plugin default locate_transcript returns None."""
        from mcp_the_force.cli_plugins.base import CLIPluginBase

        # Create a minimal concrete implementation for testing
        class MinimalPlugin(CLIPluginBase):
            @property
            def executable(self) -> str:
                return "test"

            def build_new_session_args(self, task, context_dirs, role=None, **kwargs):
                return [task]

            def build_resume_args(self, session_id, task, **kwargs):
                return [session_id, task]

            def parse_output(self, output):
                from mcp_the_force.cli_plugins.base import ParsedCLIResponse

                return ParsedCLIResponse(text="", session_id=None)

        plugin = MinimalPlugin()
        result = plugin.locate_transcript("any-id", "/any/path")
        assert result is None
