"""Tests for empty response handling in collaboration service.

Regression tests for the bug where group_think returned empty results
because the synthesis model returned empty during advisory validation,
and the code blindly accepted it without validation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_the_force.local_services.collaboration_service import CollaborationService
from mcp_the_force.types.collaboration import (
    CollaborationSession,
    DeliverableContract,
)


class TestEmptyResponseValidation:
    """Test that empty responses are handled correctly."""

    @pytest.fixture
    def mock_service(self):
        """Create a mock collaboration service with minimal setup."""
        service = CollaborationService()
        service.executor = AsyncMock()
        service.session_cache = AsyncMock()
        service.whiteboard = AsyncMock()
        return service

    @pytest.fixture
    def mock_session(self):
        """Create a mock collaboration session."""
        return CollaborationSession(
            session_id="test-session",
            objective="Test objective",
            models=["model1", "model2"],
            messages=[],
            current_step=8,
            mode="round_robin",
            max_steps=15,
            status="active",
        )

    @pytest.fixture
    def mock_contract(self):
        """Create a mock deliverable contract."""
        return DeliverableContract(
            objective="Test objective",
            output_format="Markdown report",
        )

    @pytest.mark.asyncio
    async def test_advisory_validation_retains_deliverable_on_empty_refinement(
        self, mock_service, mock_session, mock_contract
    ):
        """Regression test: Empty refinement response should retain previous deliverable.

        Bug: When synthesis model returned empty string during advisory validation,
        the code blindly replaced the good deliverable with empty, causing group_think
        to return empty results despite having a valid synthesis output.
        """
        good_deliverable = "# Valid Deliverable\n\nThis is meaningful content."

        # Mock reviewer feedback (at least one valid review)
        mock_service.executor.execute = AsyncMock(
            side_effect=[
                "Looks good, minor suggestion",  # Reviewer 1
                "Approved",  # Reviewer 2
                "",  # Empty refinement response from synthesis model
            ]
        )

        mock_service._get_tool_metadata = MagicMock(return_value={"id": "test_model"})

        with patch.object(mock_service, "session_cache") as mock_cache:
            mock_cache.set_metadata = AsyncMock()

            result = await mock_service._run_advisory_validation(
                session=mock_session,
                whiteboard_info={"store_id": "test-store"},
                contract=mock_contract,
                synthesized_deliverable=good_deliverable,
                original_models=["model1", "model2"],
                max_rounds=1,
                synthesis_model="synthesis_model",
                context=None,
                priority_context=None,
                ctx=None,
                project="test-project",
                config=None,
            )

        # Should retain the good deliverable, not the empty refinement
        assert result == good_deliverable
        assert result.strip() != ""

    @pytest.mark.asyncio
    async def test_advisory_validation_accepts_valid_refinement(
        self, mock_service, mock_session, mock_contract
    ):
        """Valid refinement responses should update the deliverable."""
        original_deliverable = "# Original\n\nOriginal content."
        refined_deliverable = "# Refined\n\nImproved content based on feedback."

        mock_service.executor.execute = AsyncMock(
            side_effect=[
                "Add more details",  # Reviewer feedback
                "Needs improvement",  # Reviewer feedback
                refined_deliverable,  # Valid refinement
            ]
        )

        mock_service._get_tool_metadata = MagicMock(return_value={"id": "test_model"})

        with patch.object(mock_service, "session_cache") as mock_cache:
            mock_cache.set_metadata = AsyncMock()

            result = await mock_service._run_advisory_validation(
                session=mock_session,
                whiteboard_info={"store_id": "test-store"},
                contract=mock_contract,
                synthesized_deliverable=original_deliverable,
                original_models=["model1", "model2"],
                max_rounds=1,
                synthesis_model="synthesis_model",
                context=None,
                priority_context=None,
                ctx=None,
                project="test-project",
                config=None,
            )

        # Should use the refined deliverable
        assert result == refined_deliverable

    @pytest.mark.asyncio
    async def test_advisory_validation_handles_whitespace_only_refinement(
        self, mock_service, mock_session, mock_contract
    ):
        """Whitespace-only refinement should also retain previous deliverable."""
        good_deliverable = "# Valid Deliverable\n\nContent."

        mock_service.executor.execute = AsyncMock(
            side_effect=[
                "Feedback",  # Reviewer
                "   \n\t  ",  # Whitespace-only refinement
            ]
        )

        mock_service._get_tool_metadata = MagicMock(return_value={"id": "test_model"})

        with patch.object(mock_service, "session_cache") as mock_cache:
            mock_cache.set_metadata = AsyncMock()

            result = await mock_service._run_advisory_validation(
                session=mock_session,
                whiteboard_info={"store_id": "test-store"},
                contract=mock_contract,
                synthesized_deliverable=good_deliverable,
                original_models=["model1"],
                max_rounds=1,
                synthesis_model="synthesis_model",
                context=None,
                priority_context=None,
                ctx=None,
                project="test-project",
                config=None,
            )

        # Should retain the good deliverable
        assert result == good_deliverable


class TestSynthesisEmptyResponse:
    """Test that synthesis phase validates non-empty response."""

    @pytest.mark.asyncio
    async def test_synthesis_raises_on_empty_response(self):
        """Synthesis phase should raise ValueError if model returns empty."""
        service = CollaborationService()
        # Create executor mock with execute method that returns empty string
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value="")  # Empty response
        service.executor = mock_executor
        service.session_cache = AsyncMock()
        service.whiteboard = AsyncMock()
        service._get_tool_metadata = MagicMock(return_value={"id": "test_model"})

        session = CollaborationSession(
            session_id="test",
            objective="test",
            models=["model1"],
            messages=[],
            current_step=5,
            mode="round_robin",
            max_steps=10,
            status="active",
        )

        contract = DeliverableContract(
            objective="Test",
            output_format="Report",
        )

        with pytest.raises(ValueError, match="returned empty response"):
            await service._run_synthesis_phase(
                session=session,
                whiteboard_info={"store_id": "test-store"},
                contract=contract,
                synthesis_model="test_model",
                context=None,
                priority_context=None,
                ctx=None,
                project="test-project",
            )
