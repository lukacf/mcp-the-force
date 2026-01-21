"""
Unit Tests: live_follow_session service.

Tests the live_follow_session functionality that allows
tailing CLI agent sessions in real-time.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLiveFollowSessionService:
    """Tests for LiveFollowSessionService."""

    @pytest.mark.asyncio
    async def test_follow_session_returns_transcript_content(self, tmp_path):
        """Service returns recent transcript content for a session."""
        from mcp_the_force.local_services.live_follow_session import (
            LiveFollowSessionService,
        )

        # Setup mock transcript
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "Working on it..."}}\n'
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "Done!"}}\n'
        )

        # Mock SessionBridge to return CLI session info
        mock_bridge = AsyncMock()
        mock_bridge.get_cli_session_id.return_value = "thread-abc-123"
        mock_bridge.get_cli_name.return_value = "codex"

        # Mock plugin to return transcript path
        mock_plugin = MagicMock()
        mock_plugin.locate_transcript.return_value = transcript

        service = LiveFollowSessionService(project_dir=str(tmp_path))
        service._session_bridge = mock_bridge

        with patch(
            "mcp_the_force.local_services.live_follow_session.get_cli_plugin",
            return_value=mock_plugin,
        ):
            result = await service.follow(
                session_id="my-task",
                lines=10,
            )

        assert "Working on it" in result
        assert "Done!" in result

    @pytest.mark.asyncio
    async def test_follow_session_returns_error_when_no_cli_session(self, tmp_path):
        """Service returns error when session has no CLI mapping."""
        from mcp_the_force.local_services.live_follow_session import (
            LiveFollowSessionService,
        )

        mock_bridge = AsyncMock()
        mock_bridge.get_cli_session_id.return_value = None
        mock_bridge.get_cli_name.return_value = None
        mock_bridge.is_session_pending.return_value = (False, None)

        service = LiveFollowSessionService(project_dir=str(tmp_path))
        service._session_bridge = mock_bridge

        result = await service.follow(session_id="nonexistent-session", lines=10)

        assert "no transcript found" in result.lower()

    @pytest.mark.asyncio
    async def test_follow_session_returns_error_when_transcript_not_found(
        self, tmp_path
    ):
        """Service returns error when transcript file cannot be located."""
        from mcp_the_force.local_services.live_follow_session import (
            LiveFollowSessionService,
        )

        mock_bridge = AsyncMock()
        mock_bridge.get_cli_session_id.return_value = "thread-abc-123"
        mock_bridge.get_cli_name.return_value = "codex"
        mock_bridge.is_session_pending.return_value = (False, None)

        mock_plugin = MagicMock()
        mock_plugin.locate_transcript.return_value = None  # Not found

        service = LiveFollowSessionService(project_dir=str(tmp_path))
        service._session_bridge = mock_bridge

        with patch(
            "mcp_the_force.local_services.live_follow_session.get_cli_plugin",
            return_value=mock_plugin,
        ):
            result = await service.follow(session_id="my-task", lines=10)

        assert "no transcript found" in result.lower()

    @pytest.mark.asyncio
    async def test_follow_session_respects_lines_limit(self, tmp_path):
        """Service respects the lines limit parameter."""
        from mcp_the_force.local_services.live_follow_session import (
            LiveFollowSessionService,
        )

        # Create transcript with many lines
        transcript = tmp_path / "session.jsonl"
        lines_data = [
            f'{{"type": "item.completed", "item": {{"type": "agent_message", "text": "Message {i}"}}}}\n'
            for i in range(50)
        ]
        transcript.write_text("".join(lines_data))

        mock_bridge = AsyncMock()
        mock_bridge.get_cli_session_id.return_value = "thread-abc-123"
        mock_bridge.get_cli_name.return_value = "codex"

        mock_plugin = MagicMock()
        mock_plugin.locate_transcript.return_value = transcript

        service = LiveFollowSessionService(project_dir=str(tmp_path))
        service._session_bridge = mock_bridge

        with patch(
            "mcp_the_force.local_services.live_follow_session.get_cli_plugin",
            return_value=mock_plugin,
        ):
            result = await service.follow(session_id="my-task", lines=5)

        # Should only have last 5 messages
        assert "Message 45" in result
        assert "Message 49" in result
        assert "Message 44" not in result

    @pytest.mark.asyncio
    async def test_follow_session_includes_tool_calls(self, tmp_path):
        """Service includes tool call information in output."""
        from mcp_the_force.local_services.live_follow_session import (
            LiveFollowSessionService,
        )

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            '{"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": "{\\"cmd\\": \\"ls -la\\"}"}}\n'
            '{"type": "response_item", "payload": {"type": "function_call_output", "output": "file1.txt"}}\n'
        )

        mock_bridge = AsyncMock()
        mock_bridge.get_cli_session_id.return_value = "thread-abc-123"
        mock_bridge.get_cli_name.return_value = "codex"

        mock_plugin = MagicMock()
        mock_plugin.locate_transcript.return_value = transcript

        service = LiveFollowSessionService(project_dir=str(tmp_path))
        service._session_bridge = mock_bridge

        with patch(
            "mcp_the_force.local_services.live_follow_session.get_cli_plugin",
            return_value=mock_plugin,
        ):
            result = await service.follow(session_id="my-task", lines=10)

        assert "exec_command" in result
        assert "ls -la" in result or "file1.txt" in result


class TestLiveFollowSessionTool:
    """Tests for live_follow_session MCP tool."""

    @pytest.mark.asyncio
    async def test_tool_calls_service(self):
        """Tool properly delegates to LiveFollowSessionService."""
        from mcp_the_force.tools.live_follow_session import live_follow_session

        with patch(
            "mcp_the_force.tools.live_follow_session.LiveFollowSessionService"
        ) as MockService:
            mock_instance = AsyncMock()
            mock_instance.follow.return_value = "Transcript content here"
            MockService.return_value = mock_instance

            result = await live_follow_session(
                session_id="test-session",
                lines=20,
            )

        mock_instance.follow.assert_called_once_with(
            session_id="test-session",
            lines=20,
        )
        assert "Transcript content" in result

    @pytest.mark.asyncio
    async def test_tool_has_default_lines_value(self):
        """Tool has sensible default for lines parameter."""
        from mcp_the_force.tools.live_follow_session import live_follow_session

        with patch(
            "mcp_the_force.tools.live_follow_session.LiveFollowSessionService"
        ) as MockService:
            mock_instance = AsyncMock()
            mock_instance.follow.return_value = "Content"
            MockService.return_value = mock_instance

            await live_follow_session(session_id="test-session")

        # Should have a default lines value (e.g., 50)
        call_kwargs = mock_instance.follow.call_args.kwargs
        assert "lines" in call_kwargs
        assert call_kwargs["lines"] >= 20  # Reasonable default


class TestLiveFollowSessionToolRegistration:
    """Tests for live_follow_session MCP tool registration."""

    def test_tool_is_registered_in_registry(self):
        """Regression test: live_follow_session tool must be registered."""
        from mcp_the_force.tools.registry import list_tools

        tools = list_tools()
        assert "live_follow_session" in tools, (
            "live_follow_session tool not registered! "
            "Ensure it's imported in mcp_the_force/tools/definitions.py"
        )

    def test_tool_has_correct_metadata(self):
        """Tool has expected metadata for MCP exposure."""
        from mcp_the_force.tools.registry import get_tool

        metadata = get_tool("live_follow_session")
        assert metadata is not None
        assert "session_id" in metadata.parameters
        assert "lines" in metadata.parameters
        assert metadata.parameters["lines"].default == 50

    def test_service_has_execute_method(self):
        """Regression test: service must have execute() for tool executor."""
        from mcp_the_force.local_services.live_follow_session import (
            LiveFollowSessionService,
        )

        service = LiveFollowSessionService(project_dir="/tmp")
        assert hasattr(
            service, "execute"
        ), "LiveFollowSessionService must have execute() method for tool executor"
        assert callable(service.execute)


class TestPendingSessionLookup:
    """Tests for pending session lookup (running sessions before completion)."""

    @pytest.mark.asyncio
    async def test_follow_finds_pending_session_by_session_id_marker(self, tmp_path):
        """Service finds transcript for pending session via session_id marker search."""
        from mcp_the_force.local_services.live_follow_session import (
            LiveFollowSessionService,
        )

        # Setup mock transcript
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            '{"type": "response_item", "payload": {"type": "message", "content": [{"type": "output_text", "text": "Working..."}]}}\n'
        )

        # Mock bridge to return pending status
        mock_bridge = AsyncMock()
        mock_bridge.get_cli_name.return_value = None  # No completed mapping
        mock_bridge.get_cli_session_id.return_value = None
        mock_bridge.is_session_pending.return_value = (True, "codex")  # Pending!

        # Mock plugin to find transcript by session_id marker
        mock_plugin = MagicMock()
        mock_plugin.find_transcript_by_session_id.return_value = transcript
        mock_plugin.locate_transcript.return_value = None

        service = LiveFollowSessionService(project_dir=str(tmp_path))
        service._session_bridge = mock_bridge

        with patch(
            "mcp_the_force.local_services.live_follow_session.get_cli_plugin",
            return_value=mock_plugin,
        ):
            result = await service.follow(session_id="my-pending-task", lines=10)

        assert "Working" in result
        mock_plugin.find_transcript_by_session_id.assert_called_once_with(
            "my-pending-task"
        )

    @pytest.mark.asyncio
    async def test_bridge_stores_and_retrieves_pending_session(self, tmp_path):
        """SessionBridge correctly handles pending session flow."""
        from mcp_the_force.cli_agents.session_bridge import SessionBridge

        bridge = SessionBridge(db_path=str(tmp_path / "sessions.db"))

        # Store pending session
        await bridge.store_pending_session(
            project="test-project",
            session_id="my-task",
            cli_name="codex",
        )

        # Verify it's detected as pending
        is_pending, cli_name = await bridge.is_session_pending(
            project="test-project",
            session_id="my-task",
        )
        assert is_pending is True
        assert cli_name == "codex"

        # Now "complete" the session with real CLI session ID
        await bridge.store_cli_session_id(
            project="test-project",
            session_id="my-task",
            cli_name="codex",
            cli_session_id="thread-real-123",
        )

        # Verify it's no longer pending
        is_pending, cli_name = await bridge.is_session_pending(
            project="test-project",
            session_id="my-task",
        )
        assert is_pending is False


class TestSessionBridgeEnhancements:
    """Tests for SessionBridge enhancements for transcript tracking."""

    @pytest.mark.asyncio
    async def test_bridge_stores_cli_name(self, tmp_path):
        """SessionBridge stores CLI name alongside session ID."""
        from mcp_the_force.cli_agents.session_bridge import SessionBridge

        bridge = SessionBridge(db_path=str(tmp_path / "sessions.db"))

        await bridge.store_cli_session_id(
            project="test-project",
            session_id="my-task",
            cli_name="codex",
            cli_session_id="thread-abc-123",
        )

        cli_name = await bridge.get_cli_name(
            project="test-project",
            session_id="my-task",
        )

        assert cli_name == "codex"

    @pytest.mark.asyncio
    async def test_bridge_returns_none_for_unknown_session(self, tmp_path):
        """SessionBridge returns None for unknown sessions."""
        from mcp_the_force.cli_agents.session_bridge import SessionBridge

        bridge = SessionBridge(db_path=str(tmp_path / "sessions.db"))

        cli_name = await bridge.get_cli_name(
            project="test-project",
            session_id="nonexistent",
        )

        assert cli_name is None
