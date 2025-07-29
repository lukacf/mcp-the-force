"""Integration tests for session management tools."""

import pytest
import json
from mcp_the_force.tools.executor import executor
from mcp_the_force.tools.registry import get_tool
from mcp_the_force.unified_session_cache import UnifiedSession, UnifiedSessionCache
import time
import os


@pytest.fixture
async def populated_test_sessions(isolate_test_databases):
    """Create test sessions for integration tests."""
    from mcp_the_force.config import get_settings

    # Get the project name that the service will use
    settings = get_settings()
    project_path = settings.logging.project_path or os.getcwd()
    project_name = os.path.basename(project_path)

    # Create test sessions
    sessions = [
        UnifiedSession(
            project=project_name,
            tool="chat_with_o3",
            session_id="integration-test-1",
            history=[{"role": "user", "content": "Integration test 1"}],
            updated_at=int(time.time()),
        ),
        UnifiedSession(
            project=project_name,
            tool="chat_with_gemini25_pro",
            session_id="integration-test-2",
            history=[{"role": "user", "content": "Integration test 2"}],
            updated_at=int(time.time()) - 10,  # Older session
        ),
    ]

    for session in sessions:
        await UnifiedSessionCache.set_session(session)

    return sessions


class TestListSessionsIntegration:
    """Integration tests for list_sessions tool."""

    async def test_list_sessions_through_executor(self, populated_test_sessions):
        """Test calling list_sessions through the executor."""
        # Get tool metadata
        metadata = get_tool("list_sessions")
        assert metadata is not None

        # Call through executor
        result = await executor.execute(metadata)

        # Result should be a JSON string
        assert isinstance(result, str)
        sessions = json.loads(result)

        # Should have our test sessions
        assert isinstance(sessions, list)
        assert len(sessions) == 2

        # Verify structure
        for session in sessions:
            assert "session_id" in session
            assert "tool_name" in session

    async def test_list_sessions_with_parameters(self, populated_test_sessions):
        """Test list_sessions with parameters through executor."""
        metadata = get_tool("list_sessions")

        # Test with limit
        result = await executor.execute(metadata, limit=1)
        sessions = json.loads(result)
        assert len(sessions) == 1

        # Test with search
        result = await executor.execute(metadata, search="integration-test-1")
        sessions = json.loads(result)
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "integration-test-1"


class TestDescribeSessionIntegration:
    """Integration tests for describe_session tool."""

    async def test_describe_session_through_executor(
        self, populated_test_sessions, mocker
    ):
        """Test calling describe_session through the executor."""
        # Mock the AI model call to avoid real API calls
        # Since get_tool is imported inside the method, we need to patch it in the registry module
        mock_get_tool = mocker.patch("mcp_the_force.tools.registry.get_tool")
        mock_get_tool.return_value = (
            None  # This will make it return "model not found" error
        )

        # Get tool metadata
        metadata = get_tool("describe_session")
        assert metadata is not None
        assert metadata.id == "describe_session"

        # Call through executor
        result = await executor.execute(
            metadata,
            session_id="integration-test-1",
            summarization_model="chat_with_gemini25_flash",
        )

        # Should return error message since we mocked get_tool to return None
        assert isinstance(result, str)
        assert (
            "Error: Summarization model 'chat_with_gemini25_flash' not found." in result
        )

    async def test_describe_session_non_existent(self, populated_test_sessions):
        """Test describe_session with non-existent session."""
        metadata = get_tool("describe_session")

        # Try to describe non-existent session
        result = await executor.execute(metadata, session_id="non-existent-session")

        # Should return error message
        assert isinstance(result, str)
        assert "Error: Session 'non-existent-session' not found." in result

    async def test_describe_session_with_cached_summary(self, populated_test_sessions):
        """Test describe_session returns cached summary when available."""
        from mcp_the_force.config import get_settings

        # Get project name
        settings = get_settings()
        project_name = os.path.basename(settings.logging.project_path or os.getcwd())

        # Set a cached summary
        await UnifiedSessionCache.set_summary(
            project_name,
            "chat_with_o3",
            "integration-test-1",
            "This is a cached summary",
        )

        metadata = get_tool("describe_session")

        # Call describe_session - should return cached summary
        result = await executor.execute(metadata, session_id="integration-test-1")

        assert result == "This is a cached summary"

    @pytest.mark.asyncio
    async def test_describe_session_full_flow_with_history(
        self, populated_test_sessions, mocker
    ):
        """Test describe_session passes conversation history to the model."""
        from mcp_the_force.local_services.describe_session import DescribeSessionService

        # Clear any cached summaries
        from mcp_the_force.unified_session_cache import (
            _get_instance as get_cache_instance,
        )

        cache = get_cache_instance()
        await cache._execute_async(
            "DELETE FROM session_summaries WHERE session_id = ?",
            ("integration-test-1",),
        )

        # Use real service without mocking
        service = DescribeSessionService()

        # In mock mode, this should work if history is passed correctly
        result = await service.execute(
            session_id="integration-test-1",
            summarization_model="chat_with_gemini25_flash",
        )

        # The result should be a proper summary, not an error about missing conversation
        print(f"Result: {result}")
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

        # Key assertions - should NOT get these errors if history was passed
        assert "provide the conversation" not in result.lower()
        assert "need the conversation" not in result.lower()
        assert (
            "conversation history" not in result.lower()
            or "summarize" in result.lower()
        )
