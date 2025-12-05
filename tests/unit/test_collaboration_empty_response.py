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
    async def test_synthesis_raises_after_all_retries_exhausted(self):
        """Synthesis phase should raise RuntimeError after all retries and fallbacks fail."""
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

        # Now raises RuntimeError after all retries and fallbacks exhausted
        with pytest.raises(RuntimeError, match="All models failed after retries"):
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

    @pytest.mark.asyncio
    async def test_synthesis_succeeds_with_fallback_model(self):
        """Synthesis should succeed if fallback model returns valid response."""
        service = CollaborationService()

        # First model fails, fallback succeeds
        call_count = 0

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1
            # First 4 calls fail (2 retries x 2 models), 5th succeeds
            if call_count <= 4:
                return ""
            return "Valid synthesis output"

        mock_executor = MagicMock()
        mock_executor.execute = mock_execute
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

        result = await service._run_synthesis_phase(
            session=session,
            whiteboard_info={"store_id": "test-store"},
            contract=contract,
            synthesis_model="test_model",
            context=None,
            priority_context=None,
            ctx=None,
            project="test-project",
        )

        assert result == "Valid synthesis output"


class TestRetryWithFallback:
    """Test retry logic with model fallback."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self):
        """Retry should succeed if second attempt returns valid response."""
        service = CollaborationService()

        call_count = 0

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ""  # First attempt fails
            return "Success on retry"

        mock_executor = MagicMock()
        mock_executor.execute = mock_execute
        service.executor = mock_executor
        service._get_tool_metadata = MagicMock(return_value={"id": "test_model"})

        response, model_used = await service._execute_with_retry(
            model="test_model",
            instructions="test",
            output_format="text",
            session_id="test-session",
            timeout=60,
        )

        assert response == "Success on retry"
        assert model_used == "test_model"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_succeeds_with_fallback_model(self):
        """Retry should use fallback model after primary fails."""
        service = CollaborationService()

        call_count = 0

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1
            # First 2 attempts (primary model) fail, 3rd (first fallback) succeeds
            if call_count <= 2:
                return ""
            return "Fallback success"

        mock_executor = MagicMock()
        mock_executor.execute = mock_execute
        service.executor = mock_executor
        service._get_tool_metadata = MagicMock(return_value={"id": "model"})

        response, model_used = await service._execute_with_retry(
            model="primary_model",
            instructions="test",
            output_format="text",
            session_id="test-session",
            timeout=60,
            fallback_models=["fallback_model"],
        )

        assert response == "Fallback success"
        assert model_used == "fallback_model"

    @pytest.mark.asyncio
    async def test_retry_handles_exception(self):
        """Retry should handle exceptions and try again."""
        service = CollaborationService()

        call_count = 0

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("API error")
            return "Success after error"

        mock_executor = MagicMock()
        mock_executor.execute = mock_execute
        service.executor = mock_executor
        service._get_tool_metadata = MagicMock(return_value={"id": "model"})

        response, model_used = await service._execute_with_retry(
            model="test_model",
            instructions="test",
            output_format="text",
            session_id="test-session",
            timeout=60,
        )

        assert response == "Success after error"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_advisory_validation_retry_preserves_deliverable(self):
        """Advisory validation should preserve deliverable even after retry succeeds."""
        service = CollaborationService()

        call_count = 0

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1
            # Reviewer feedback (first 2 calls)
            if call_count <= 2:
                return "Good feedback"
            # Refinement: first attempt fails, second succeeds
            if call_count == 3:
                return ""  # Empty
            return "Refined deliverable"

        mock_executor = MagicMock()
        mock_executor.execute = mock_execute
        service.executor = mock_executor
        service.session_cache = AsyncMock()
        service._get_tool_metadata = MagicMock(return_value={"id": "model"})

        session = CollaborationSession(
            session_id="test",
            objective="test",
            models=["model1", "model2"],
            messages=[],
            current_step=8,
            mode="round_robin",
            max_steps=15,
            status="active",
        )

        contract = DeliverableContract(
            objective="Test",
            output_format="Report",
        )

        result = await service._run_advisory_validation(
            session=session,
            whiteboard_info={"store_id": "test-store"},
            contract=contract,
            synthesized_deliverable="Original deliverable",
            original_models=["model1", "model2"],
            max_rounds=1,
            synthesis_model="synthesis_model",
            context=None,
            priority_context=None,
            ctx=None,
            project="test-project",
            config=None,
        )

        # Should get the refined deliverable after retry succeeded
        assert result == "Refined deliverable"
