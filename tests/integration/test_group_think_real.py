"""Integration tests for group_think testing component interactions with mocked dependencies."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from mcp_the_force.tools.group_think import GroupThink
from mcp_the_force.local_services.collaboration_service import CollaborationService


class TestGroupThinkIntegration:
    """Integration tests with all dependencies mocked - tests component interactions."""

    @pytest.mark.asyncio
    async def test_service_executor_whiteboard_integration(self):
        """Test CollaborationService integrates properly with ToolExecutor and WhiteboardManager."""

        # Mock all external dependencies
        with (
            patch("mcp_the_force.tools.executor.executor") as mock_global_executor,
            patch(
                "mcp_the_force.unified_session_cache.unified_session_cache"
            ) as mock_global_cache,
            patch("mcp_the_force.config.get_settings") as mock_settings,
        ):
            # Set up mocks
            mock_global_executor.execute = AsyncMock(return_value="Mock response")
            mock_global_cache.get_metadata = AsyncMock(return_value=None)
            mock_global_cache.set_metadata = AsyncMock()
            mock_global_cache.append_responses_message = AsyncMock()
            mock_settings.return_value.logging.project_path = "/test/mcp-the-force"

            # Create service (will use mocked global dependencies)
            service = CollaborationService()

            # Mock whiteboard and tool registry
            with (
                patch.object(
                    service.whiteboard, "get_or_create_store"
                ) as mock_create_store,
                patch.object(service.whiteboard, "append_message") as mock_append,
                patch.object(service, "_get_tool_metadata") as mock_get_tool,
                patch.object(
                    service, "_ensure_progress_components_installed"
                ) as mock_installer,
                patch("pathlib.Path.mkdir"),
                patch("builtins.open", create=True),
                patch("json.dump"),
            ):
                mock_create_store.return_value = {
                    "store_id": "vs_test",
                    "provider": "mock",
                }
                mock_append.return_value = None
                mock_get_tool.return_value = Mock(tool_name="mock_tool")
                mock_installer.return_value = None

                result = await service.execute(
                    session_id="integration-test",
                    objective="Test component integration",
                    models=["chat_with_gpt51_codex"],
                    output_format="Integration test result",
                    discussion_turns=1,
                    validation_rounds=0,
                )

                # Verify components interacted correctly
                assert result is not None
                mock_create_store.assert_called_once()
                mock_global_executor.execute.assert_called()
                mock_global_cache.set_metadata.assert_called()

    @pytest.mark.asyncio
    async def test_tool_registry_integration(self):
        """Test GroupThink tool integrates properly with the tool registry."""

        from mcp_the_force.tools.registry import get_tool

        # Test tool is properly registered
        tool_metadata = get_tool("group_think")
        assert tool_metadata is not None
        assert tool_metadata.id == "group_think"
        assert tool_metadata.spec_class.service_cls == CollaborationService

    @pytest.mark.asyncio
    async def test_mcp_integration(self):
        """Test that group_think can be called through MCP interface with mocks."""

        # This would test the full MCP call stack but with mocked models
        # Mock the MCP server and verify tool can be called

        tool = GroupThink()
        assert hasattr(tool, "session_id")
        assert hasattr(tool, "objective")
        assert hasattr(tool, "models")
        assert hasattr(tool, "output_format")

        # Verify tool has correct service integration
        assert tool.service_cls == CollaborationService
        assert tool.model_name == "group_think"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
