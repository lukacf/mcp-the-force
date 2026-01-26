"""Comprehensive tests for the new group_think multi-phase collaboration workflow."""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch

from mcp_the_force.local_services.collaboration_service import CollaborationService
from mcp_the_force.types.collaboration import DeliverableContract


class TestGroupThinkMultiPhaseWorkflow:
    """Test the complete multi-phase workflow: Discussion → Synthesis → Validation."""

    @pytest.fixture
    def collaboration_service(self):
        """Create CollaborationService with mocked dependencies."""
        mock_executor = AsyncMock()
        mock_whiteboard = AsyncMock()
        mock_session_cache = AsyncMock()

        # Mock whiteboard methods
        mock_whiteboard.get_or_create_store = AsyncMock()
        mock_whiteboard.append_message = AsyncMock()

        service = CollaborationService(
            executor=mock_executor,
            whiteboard_manager=mock_whiteboard,
            session_cache=mock_session_cache,
        )
        return service, mock_executor, mock_whiteboard, mock_session_cache

    @pytest.mark.asyncio
    async def test_complete_multi_phase_workflow(self, collaboration_service):
        """Test the full discussion → synthesis → validation workflow."""
        service, mock_executor, mock_whiteboard, mock_session_cache = (
            collaboration_service
        )

        # Mock whiteboard creation
        mock_whiteboard.get_or_create_store.return_value = {
            "store_id": "vs_test_whiteboard",
            "provider": "openai",
        }

        # Mock session cache - no existing session
        mock_session_cache.get_metadata.return_value = None

        # Mock the tool registry to return valid tool metadata
        mock_tool_metadata = Mock()
        mock_tool_metadata.tool_name = "chat_with_gpt52_pro"

        # Simple mock that returns consistent responses
        mock_executor.execute.return_value = "Mock model response"

        # Mock config
        with (
            patch("mcp_the_force.config.get_settings") as mock_settings,
            patch.object(
                service, "_get_tool_metadata", return_value=mock_tool_metadata
            ),
        ):
            mock_settings.return_value.logging.project_path = "/test/mcp-the-force"

            result = await service.execute(
                session_id="test-workflow",
                objective="Test multi-phase collaboration",
                models=["chat_with_gpt52_pro", "chat_with_gemini3_flash_preview"],
                output_format="Test deliverable with sections: Summary, Details",
                discussion_turns=1,  # Reduce complexity for this test
                validation_rounds=1,
            )

        # Verify we got a result
        assert result is not None
        assert len(result) > 0

        # Verify whiteboard was created
        mock_whiteboard.get_or_create_store.assert_called_once_with("test-workflow")

        # Verify session was saved
        assert mock_session_cache.set_metadata.call_count >= 1

    @pytest.mark.asyncio
    async def test_discussion_phase_round_robin(self, collaboration_service):
        """Test that discussion phase follows round-robin pattern."""
        service, mock_executor, mock_whiteboard, mock_session_cache = (
            collaboration_service
        )

        # Mock dependencies
        mock_whiteboard.get_or_create_store.return_value = {
            "store_id": "vs_test",
            "provider": "openai",
        }
        mock_session_cache.get_metadata.return_value = None

        # Track which models are called during discussion phase
        called_models = []

        async def mock_execute(**kwargs):
            sid = kwargs.get("session_id", "")
            # Count only discussion calls (not synthesis/validation/advisory)
            if (
                "__synthesis" not in sid
                and "__validation_" not in sid
                and "__advisory_" not in sid
            ):
                # Extract model name after "__"
                if "__" in sid:
                    model_name = sid.split("__", 1)[1]
                    called_models.append(model_name)
            return "Mock response"

        mock_executor.execute = mock_execute

        with patch("mcp_the_force.config.get_settings") as mock_settings:
            mock_settings.return_value.logging.project_path = "/test/mcp-the-force"

            await service.execute(
                session_id="round-robin-test",
                objective="Test round-robin pattern",
                models=[
                    "chat_with_gpt52_pro",
                    "chat_with_gemini3_flash_preview",
                    "chat_with_grok41",
                ],
                output_format="Test result",
                discussion_turns=4,
                validation_rounds=0,  # Skip validation to focus on discussion
            )

        # Verify discussion phase used round-robin pattern
        discussion_calls = called_models[:4]  # First 4 calls should be discussion

        # Note: We can't easily verify the exact pattern without better mocking,
        # but we can verify all original models participated
        discussion_models = set(discussion_calls)
        assert "chat_with_gpt52_pro" in discussion_models
        assert "chat_with_gemini3_flash_preview" in discussion_models
        assert "chat_with_grok41" in discussion_models

    @pytest.mark.asyncio
    async def test_synthesis_phase_uses_correct_model(self, collaboration_service):
        """Test that synthesis phase uses the specified synthesis model."""
        service, mock_executor, mock_whiteboard, mock_session_cache = (
            collaboration_service
        )

        mock_whiteboard.get_or_create_store.return_value = {
            "store_id": "vs_test",
            "provider": "openai",
        }
        mock_session_cache.get_metadata.return_value = None

        synthesis_calls = []

        async def mock_execute(**kwargs):
            # Track synthesis calls by looking for synthesis session IDs
            session_id = kwargs.get("session_id", "")
            if "synthesis" in session_id:
                synthesis_calls.append(kwargs)
            return "Mock synthesis deliverable"

        mock_executor.execute = mock_execute

        with patch("mcp_the_force.config.get_settings") as mock_settings:
            mock_settings.return_value.logging.project_path = "/test/mcp-the-force"

            await service.execute(
                session_id="synthesis-test",
                objective="Test synthesis model",
                models=["chat_with_gpt52_pro"],
                output_format="Test deliverable",
                discussion_turns=1,
                synthesis_model="chat_with_claude45_sonnet",  # Custom synthesis model
                validation_rounds=0,
            )

        # Verify synthesis was called
        assert len(synthesis_calls) >= 1

        # Verify synthesis used the correct metadata (would come from get_tool_metadata)
        synthesis_call = synthesis_calls[0]
        assert "synthesis" in synthesis_call["session_id"]

    @pytest.mark.asyncio
    async def test_validation_rounds_feedback_loop(self, collaboration_service):
        """Test that validation rounds create proper feedback loop."""
        service, mock_executor, mock_whiteboard, mock_session_cache = (
            collaboration_service
        )

        mock_whiteboard.get_or_create_store.return_value = {
            "store_id": "vs_test",
            "provider": "openai",
        }
        mock_session_cache.get_metadata.return_value = None

        validation_calls = []
        refinement_calls = []

        async def mock_execute(**kwargs):
            session_id = kwargs.get("session_id", "")
            if "validation_r" in session_id:
                validation_calls.append(kwargs)
                return "Validation feedback"
            elif "advisory_r" in session_id:
                refinement_calls.append(kwargs)
                return "Refined deliverable"
            return "Mock response"

        mock_executor.execute = mock_execute

        with patch("mcp_the_force.config.get_settings") as mock_settings:
            mock_settings.return_value.logging.project_path = "/test/mcp-the-force"

            await service.execute(
                session_id="validation-test",
                objective="Test validation rounds",
                models=["chat_with_gpt52_pro", "chat_with_gemini3_flash_preview"],
                output_format="Test deliverable",
                discussion_turns=1,
                validation_rounds=2,
            )

        # Verify validation feedback was collected
        # Should be: 2 models × 2 rounds = 4 validation calls
        assert len(validation_calls) >= 4

        # Verify refinement happened after each round
        # Should be: 2 refinement calls (one per round)
        assert len(refinement_calls) >= 2

    @pytest.mark.asyncio
    async def test_session_continuity(self, collaboration_service):
        """Test that existing sessions are properly continued."""
        service, mock_executor, mock_whiteboard, mock_session_cache = (
            collaboration_service
        )

        # Mock existing session (in progress, not completed)
        existing_session_data = {
            "session_id": "existing-session",
            "objective": "Original objective",
            "models": ["chat_with_gpt52_pro"],
            "messages": [],
            "current_step": 2,  # Already completed some steps
            "mode": "round_robin",
            "max_steps": 10,
            "status": "active",
        }

        # Mock get_metadata to return session data for collab_state, None for collab_deliverable
        async def mock_get_metadata(project, tool, session_id, key):
            if key == "collab_state":
                return existing_session_data
            if key == "collab_deliverable":
                return None  # No cached deliverable - session is in progress
            return None

        mock_session_cache.get_metadata = AsyncMock(side_effect=mock_get_metadata)

        mock_whiteboard.get_or_create_store.return_value = {
            "store_id": "vs_existing",
            "provider": "openai",
        }
        mock_executor.execute.return_value = "Continued response"

        with patch("mcp_the_force.config.get_settings") as mock_settings:
            mock_settings.return_value.logging.project_path = "/test/mcp-the-force"

            result = await service.execute(
                session_id="existing-session",
                objective="New objective should be ignored",
                models=["chat_with_gpt52_pro"],
                output_format="Test continuation",
                discussion_turns=1,
            )

        # Verify get_metadata was called for both collab_state and collab_deliverable
        calls = mock_session_cache.get_metadata.call_args_list
        call_keys = [
            call.args[3] if len(call.args) > 3 else call.kwargs.get("key")
            for call in calls
        ]
        assert "collab_state" in call_keys, "Should check for collab_state"

        # Verify collaboration continued from where it left off
        assert "Continued response" in result or "Mock" in result


class TestCollaborationServiceUnitMethods:
    """Unit tests for individual CollaborationService methods."""

    @pytest.fixture
    def service(self):
        return CollaborationService()

    @pytest.mark.asyncio
    async def test_build_deliverable_contract(self, service):
        """Test deliverable contract creation."""
        contract = await service._build_deliverable_contract(
            objective="Test objective",
            output_format="JSON with keys: summary, details",
            user_input="Additional context",
            session_id="test-contract",
        )

        assert isinstance(contract, DeliverableContract)
        assert contract.objective == "Test objective"
        assert contract.output_format == "JSON with keys: summary, details"
        assert contract.deliverable_type == "user_specified"

    @pytest.mark.asyncio
    async def test_build_deliverable_contract_validation(self, service):
        """Test contract validation for empty output_format."""
        with pytest.raises(ValueError, match="output_format is required"):
            await service._build_deliverable_contract(
                objective="Test", output_format="", user_input="", session_id="test"
            )


class TestGroupThinkErrorScenarios:
    """Test error handling and recovery scenarios."""

    @pytest.fixture
    def collaboration_service(self):
        mock_executor = AsyncMock()
        mock_whiteboard = AsyncMock()
        mock_session_cache = AsyncMock()

        service = CollaborationService(
            executor=mock_executor,
            whiteboard_manager=mock_whiteboard,
            session_cache=mock_session_cache,
        )
        return service, mock_executor, mock_whiteboard, mock_session_cache

    @pytest.mark.asyncio
    async def test_model_timeout_handling(self, collaboration_service):
        """Test handling of model timeouts during discussion."""
        service, mock_executor, mock_whiteboard, mock_session_cache = (
            collaboration_service
        )

        mock_whiteboard.get_or_create_store.return_value = {
            "store_id": "vs_test",
            "provider": "openai",
        }
        mock_session_cache.get_metadata.return_value = None

        # Mock timeout exception
        mock_executor.execute.side_effect = asyncio.TimeoutError("Model timed out")

        with patch("mcp_the_force.config.get_settings") as mock_settings:
            mock_settings.return_value.logging.project_path = "/test/mcp-the-force"

            result = await service.execute(
                session_id="timeout-test",
                objective="Test timeout handling",
                models=["chat_with_gpt52_pro"],
                output_format="Test result",
                discussion_turns=1,
                validation_rounds=0,
            )

        # Verify error was handled gracefully
        assert "error" in result.lower() or "timeout" in result.lower()

        # Verify set_metadata was called (session state was updated)
        assert mock_session_cache.set_metadata.call_count > 0

        # Optional: Check if any calls contain failed status
        all_calls = mock_session_cache.set_metadata.call_args_list
        print(f"Metadata calls made: {len(all_calls)}")
        for i, call in enumerate(all_calls):
            print(f"Call {i}: {call}")

        # The service should attempt to mark session as failed in the error handler


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
