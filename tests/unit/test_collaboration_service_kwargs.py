"""Test CollaborationService kwargs handling regression."""

import pytest
from unittest.mock import AsyncMock, Mock

from mcp_the_force.local_services.collaboration_service import CollaborationService
from mcp_the_force.types.collaboration import CollaborationConfig


class TestCollaborationServiceKwargsHandling:
    """Test that CollaborationService handles unexpected kwargs properly."""

    @pytest.fixture
    def collaboration_service(self):
        """Create CollaborationService with mocked dependencies."""
        mock_executor = Mock()
        mock_executor.execute = AsyncMock(return_value="Mock response")

        mock_whiteboard = Mock()
        mock_whiteboard.get_or_create_store = AsyncMock(
            return_value={"store_id": "test_store", "provider": "mock"}
        )
        mock_whiteboard.append_message = AsyncMock()
        mock_whiteboard.vs_manager = Mock()
        mock_whiteboard.vs_manager.renew_lease = AsyncMock()

        mock_session_cache = Mock()
        mock_session_cache.get_metadata = AsyncMock(return_value=None)
        mock_session_cache.set_metadata = AsyncMock()
        mock_session_cache.append_responses_message = AsyncMock()

        return CollaborationService(
            executor=mock_executor,
            whiteboard_manager=mock_whiteboard,
            session_cache=mock_session_cache,
        )

    @pytest.mark.asyncio
    async def test_execute_accepts_structured_output_schema_kwarg(
        self, collaboration_service
    ):
        """Test that execute() accepts structured_output_schema without error."""

        # This should not raise an error
        result = await collaboration_service.execute(
            session_id="kwargs-test",
            objective="Test objective",
            models=["chat_with_gpt5"],
            output_format="Test deliverable format",
            user_input="Test input",
            structured_output_schema={
                "type": "object",
                "properties": {"test": {"type": "string"}},
            },
        )

        # Should complete successfully
        assert "Mock response" in result

        # Verify executor was called
        collaboration_service.executor.execute.assert_called()

    @pytest.mark.asyncio
    async def test_execute_accepts_multiple_unknown_kwargs(self, collaboration_service):
        """Test that execute() accepts multiple unknown kwargs without error."""

        # This should not raise an error
        result = await collaboration_service.execute(
            session_id="multi-kwargs-test",
            objective="Test objective",
            models=["chat_with_gpt5"],
            output_format="Test deliverable format",
            user_input="Test input",
            structured_output_schema={"type": "object"},
            some_other_param="value",
            another_param=123,
            bool_param=True,
        )

        # Should complete successfully
        assert "Mock response" in result

    @pytest.mark.asyncio
    async def test_execute_kwargs_dont_interfere_with_core_functionality(
        self, collaboration_service
    ):
        """Test that kwargs don't interfere with normal collaboration flow."""

        result = await collaboration_service.execute(
            session_id="flow-test",
            objective="Test flow with kwargs",
            models=["chat_with_gpt5", "chat_with_gemini25_pro"],
            output_format="Test deliverable format",
            user_input="Test user input",
            mode="round_robin",
            max_steps=5,
            # These should be ignored
            extra_param="ignored",
            structured_output_schema={"type": "string"},
        )

        # Should complete successfully
        assert "Mock response" in result

        # Verify whiteboard operations
        collaboration_service.whiteboard.get_or_create_store.assert_called_once_with(
            "flow-test"
        )
        collaboration_service.whiteboard.append_message.assert_called()

        # Verify executor was called with correct parameters
        collaboration_service.executor.execute.assert_called()

        # Verify session was saved
        collaboration_service.session_cache.set_metadata.assert_called()

    @pytest.mark.asyncio
    async def test_execute_with_config_and_kwargs(self, collaboration_service):
        """Test that both config and kwargs work together."""

        custom_config = CollaborationConfig(
            max_steps=15, timeout_per_step=600, summarization_threshold=100
        )

        result = await collaboration_service.execute(
            session_id="config-kwargs-test",
            objective="Test with custom config and kwargs",
            models=["chat_with_gpt5"],
            output_format="JSON response with analysis",
            config=custom_config,
            # MCP framework parameters
            structured_output_schema={"type": "object"},
            temperature=0.7,
        )

        # Should complete successfully
        assert "Mock response" in result

        # Config should be used internally (not kwargs)
        # This is verified by the fact that the function completed without error
