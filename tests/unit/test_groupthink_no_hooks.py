"""Tests to verify GroupThink works without Claude Code hook/chatter progress code.

These tests ensure that:
1. CollaborationService has no hook-related methods
2. No chatter progress file writing occurs
3. No auto-installation of progress components
4. GroupThink executes without Claude Code specific dependencies
"""

import pytest
import inspect
from unittest.mock import MagicMock, AsyncMock, patch


class TestCollaborationServiceNoHooks:
    """Verify CollaborationService has no hook-related code."""

    def test_no_write_progress_file_method(self):
        """CollaborationService should not have _write_progress_file method."""
        from mcp_the_force.local_services.collaboration_service import (
            CollaborationService,
        )

        assert not hasattr(
            CollaborationService, "_write_progress_file"
        ), "CollaborationService should not have _write_progress_file method"

    def test_no_cleanup_progress_file_method(self):
        """CollaborationService should not have _cleanup_progress_file method."""
        from mcp_the_force.local_services.collaboration_service import (
            CollaborationService,
        )

        assert not hasattr(
            CollaborationService, "_cleanup_progress_file"
        ), "CollaborationService should not have _cleanup_progress_file method"

    def test_no_ensure_progress_components_method(self):
        """CollaborationService should not have _ensure_progress_components_installed method."""
        from mcp_the_force.local_services.collaboration_service import (
            CollaborationService,
        )

        assert not hasattr(
            CollaborationService, "_ensure_progress_components_installed"
        ), "CollaborationService should not have _ensure_progress_components_installed method"

    def test_no_chatter_imports(self):
        """CollaborationService should not import chatter-related modules."""
        import mcp_the_force.local_services.collaboration_service as collab_module

        source = inspect.getsource(collab_module)

        # Should not have any chatter-related imports or references
        assert (
            "chatter_progress" not in source.lower()
        ), "CollaborationService should not reference chatter_progress"
        assert (
            "ChatterProgressInstaller" not in source
        ), "CollaborationService should not import ChatterProgressInstaller"


class TestChatterProgressInstallerRemoved:
    """Verify chatter progress installer tool is removed."""

    def test_install_chatter_progress_tool_not_registered(self):
        """install_chatter_progress tool should not be registered."""
        from mcp_the_force.tools.registry import list_tools

        tools = list_tools()
        tool_names = [
            t.model_name if hasattr(t, "model_name") else str(t) for t in tools
        ]

        assert (
            "install_chatter_progress" not in tool_names
        ), "install_chatter_progress tool should not be registered"


class TestGroupThinkExecutesWithoutHooks:
    """Verify GroupThink can execute without any hook dependencies."""

    @pytest.mark.asyncio
    async def test_execute_no_progress_file_created(self, tmp_path):
        """GroupThink execution should not create any progress files."""
        from mcp_the_force.local_services.collaboration_service import (
            CollaborationService,
        )

        # Create mock dependencies
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value="Mock response")

        mock_whiteboard = MagicMock()
        mock_whiteboard.get_or_create_store = AsyncMock(
            return_value={"store_id": "test_store"}
        )
        mock_whiteboard.append_message = AsyncMock()

        mock_session_cache = MagicMock()
        mock_session_cache.get_metadata = AsyncMock(return_value=None)
        mock_session_cache.set_metadata = AsyncMock()
        mock_session_cache.append_responses_message = AsyncMock()

        service = CollaborationService(
            executor=mock_executor,
            whiteboard_manager=mock_whiteboard,
            session_cache=mock_session_cache,
        )

        # Mock settings to use tmp_path
        with patch("mcp_the_force.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.logging.project_path = str(tmp_path)
            mock_settings.return_value = settings

            # Execute a minimal collaboration
            result = await service.execute(
                session_id="test-session",
                objective="Test objective",
                models=["chat_with_gpt52"],
                output_format="Plain text",
                discussion_turns=1,
                validation_rounds=0,
            )

        # Verify no progress files were created
        claude_dir = tmp_path / ".claude"
        if claude_dir.exists():
            progress_file = claude_dir / "chatter_progress.json"
            assert (
                not progress_file.exists()
            ), "No chatter_progress.json should be created"

            chatter_dir = claude_dir / "chatter"
            assert not chatter_dir.exists(), "No chatter directory should be created"

        # Ensure result was returned (not None or error)
        assert result is not None
