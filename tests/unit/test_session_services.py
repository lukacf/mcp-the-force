"""Unit tests for session management services."""

import pytest
import time
import os
from mcp_the_force.local_services.list_sessions import ListSessionsService
from mcp_the_force.unified_session_cache import UnifiedSession, UnifiedSessionCache


@pytest.fixture
async def populated_session_db(isolate_test_databases):
    """Fixture that populates test database with sessions."""
    import os
    from mcp_the_force.config import get_settings

    # Get the project name that the service will use
    settings = get_settings()
    project_path = settings.logging.project_path or os.getcwd()
    project_name = os.path.basename(project_path)

    # Create a few test sessions with the correct project name
    session1 = UnifiedSession(
        project=project_name,
        tool="chat_with_o3",
        session_id="test-session-1",
        history=[{"role": "user", "content": "Hello"}],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(session1)

    session2 = UnifiedSession(
        project=project_name,
        tool="chat_with_gemini25_pro",
        session_id="test-session-2",
        history=[{"role": "user", "content": "Test query"}],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(session2)

    # Create a session with a summary for testing JOIN
    summary_session = UnifiedSession(
        project=project_name,
        tool="chat_with_gpt41",
        session_id="test-session-with-summary",
        history=[{"role": "user", "content": "Long conversation"}],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(summary_session)

    # This will be added later when we implement summary caching
    # await UnifiedSessionCache.set_summary(
    #     summary_session.project,
    #     summary_session.tool,
    #     summary_session.session_id,
    #     "This is a cached summary."
    # )


class TestListSessionsService:
    """Tests for ListSessionsService."""

    async def test_list_sessions_empty_db(self, isolate_test_databases):
        """Test list_sessions returns empty list when no sessions exist."""
        service = ListSessionsService()
        result = await service.execute()

        assert result == []

    async def test_list_sessions_returns_data(self, populated_session_db):
        """Test list_sessions returns sessions from database."""
        service = ListSessionsService()
        result = await service.execute()

        # Should return all 3 sessions
        assert len(result) == 3

        # Each session should have session_id and tool_name
        for session in result:
            assert "session_id" in session
            assert "tool_name" in session
            assert isinstance(session["session_id"], str)
            assert isinstance(session["tool_name"], str)

        # Check specific sessions are present
        session_ids = [s["session_id"] for s in result]
        assert "test-session-1" in session_ids
        assert "test-session-2" in session_ids
        assert "test-session-with-summary" in session_ids

    async def test_list_sessions_with_limit(self, populated_session_db):
        """Test list_sessions respects limit parameter."""
        service = ListSessionsService()

        # Test with limit=2
        result = await service.execute(limit=2)
        assert len(result) == 2

        # Test with limit=1
        result = await service.execute(limit=1)
        assert len(result) == 1

        # Test with limit=10 (more than available)
        result = await service.execute(limit=10)
        assert len(result) == 3  # Only 3 sessions exist

    async def test_list_sessions_with_search(self, populated_session_db):
        """Test list_sessions respects search parameter."""
        service = ListSessionsService()

        # Search by session_id substring
        result = await service.execute(search="session-1")
        assert len(result) == 1
        assert result[0]["session_id"] == "test-session-1"

        # Search by tool name substring
        result = await service.execute(search="gemini")
        assert len(result) == 1
        assert result[0]["tool_name"] == "chat_with_gemini25_pro"

        # Search that matches multiple sessions
        result = await service.execute(search="test-session")
        assert len(result) == 3

        # Search with no matches
        result = await service.execute(search="nonexistent")
        assert len(result) == 0

    async def test_list_sessions_with_summary_join(self, populated_session_db):
        """Test list_sessions with include_summary parameter."""
        # First add a summary to one of the sessions
        from mcp_the_force.config import get_settings

        settings = get_settings()
        project_name = os.path.basename(settings.logging.project_path or os.getcwd())

        await UnifiedSessionCache.set_summary(
            project_name, "chat_with_o3", "test-session-1", "This is a test summary"
        )

        service = ListSessionsService()

        # Test without include_summary
        result = await service.execute(include_summary=False)
        assert len(result) > 0
        for session in result:
            assert "summary" not in session

        # Test with include_summary
        result = await service.execute(include_summary=True)
        assert len(result) > 0

        # Find the session with summary
        session_with_summary = None
        for session in result:
            assert "summary" in session  # Field should exist for all
            if session["session_id"] == "test-session-1":
                session_with_summary = session

        assert session_with_summary is not None
        assert session_with_summary["summary"] == "This is a test summary"

        # Other sessions should have None summary
        for session in result:
            if session["session_id"] != "test-session-1":
                assert session["summary"] is None


class TestDescribeSessionService:
    """Tests for DescribeSessionService."""

    async def test_describe_non_existent_session(self, isolate_test_databases):
        """Test describe_session returns error for non-existent session."""
        from mcp_the_force.local_services.describe_session import DescribeSessionService

        service = DescribeSessionService()
        result = await service.execute(session_id="non-existent-session")

        assert result == "Error: Session 'non-existent-session' not found."

    async def test_describe_cache_hit(self, populated_session_db, mocker):
        """Test describe_session returns cached summary when available."""
        from mcp_the_force.local_services.describe_session import DescribeSessionService
        from mcp_the_force.config import get_settings

        # Get project name
        settings = get_settings()
        project_name = os.path.basename(settings.logging.project_path or os.getcwd())

        # Mock get_summary to return a cached summary
        mock_get_summary = mocker.patch(
            "mcp_the_force.unified_session_cache.UnifiedSessionCache.get_summary"
        )
        mock_get_summary.return_value = "Cached summary from database"

        # Mock executor to fail if called (it shouldn't be)
        mock_executor = mocker.patch("mcp_the_force.tools.executor.executor.execute")
        mock_executor.side_effect = Exception(
            "Executor should not be called on cache hit"
        )

        service = DescribeSessionService()
        result = await service.execute(session_id="test-session-1")

        # Should return the cached summary
        assert result == "Cached summary from database"

        # Verify get_summary was called with correct parameters
        mock_get_summary.assert_called_once_with(
            project_name, "chat_with_o3", "test-session-1"
        )

        # Verify executor was NOT called
        mock_executor.assert_not_called()

    async def test_describe_cache_miss_duplicates_and_executes(
        self, populated_session_db, mocker
    ):
        """Test describe_session duplicates session and calls executor on cache miss."""
        from mcp_the_force.local_services.describe_session import DescribeSessionService
        from mcp_the_force.config import get_settings

        # Get project name
        settings = get_settings()
        project_name = os.path.basename(settings.logging.project_path or os.getcwd())

        # Mock get_summary to return None (cache miss)
        mock_get_summary = mocker.patch(
            "mcp_the_force.unified_session_cache.UnifiedSessionCache.get_summary"
        )
        mock_get_summary.return_value = None

        # Mock set_session to capture the duplicated session
        mock_set_session = mocker.patch(
            "mcp_the_force.unified_session_cache.UnifiedSessionCache.set_session"
        )

        # Mock set_summary to capture the cached summary
        mock_set_summary = mocker.patch(
            "mcp_the_force.unified_session_cache.UnifiedSessionCache.set_summary"
        )

        # Mock executor to return a summary
        mock_executor = mocker.patch("mcp_the_force.tools.executor.executor.execute")
        mock_executor.return_value = "This is a generated summary of the session."

        service = DescribeSessionService()
        result = await service.execute(
            session_id="test-session-1",
            summarization_model="chat_with_gemini25_flash",
            extra_instructions="Be concise",
        )

        # Should return the generated summary
        assert result == "This is a generated summary of the session."

        # Verify set_session was called with a temp session
        mock_set_session.assert_called_once()
        temp_session = mock_set_session.call_args[0][0]
        assert temp_session.session_id.startswith("temp-summary-")
        assert temp_session.project == project_name
        assert temp_session.tool == "chat_with_o3"

        # Verify executor was called with the temp session and model
        mock_executor.assert_called_once()
        metadata = mock_executor.call_args[0][0]
        kwargs = mock_executor.call_args[1]
        assert metadata.id == "chat_with_gemini25_flash"
        assert kwargs["session_id"].startswith("temp-summary-")

        # Verify summary was cached for the original session
        mock_set_summary.assert_called_once_with(
            project_name,
            "chat_with_o3",
            "test-session-1",
            "This is a generated summary of the session.",
        )

    async def test_describe_session_passes_history_in_instructions(
        self, populated_session_db, mocker
    ):
        """Test that describe_session includes conversation history in the instructions."""
        from mcp_the_force.local_services.describe_session import DescribeSessionService

        # Mock get_summary to return None (cache miss)
        mock_get_summary = mocker.patch(
            "mcp_the_force.unified_session_cache.UnifiedSessionCache.get_summary"
        )
        mock_get_summary.return_value = None

        # Don't mock the executor - let's spy on it instead
        mock_executor = mocker.patch("mcp_the_force.tools.executor.executor.execute")
        mock_executor.return_value = "Summary"

        service = DescribeSessionService()
        await service.execute(session_id="test-session-1")

        # Verify executor was called
        mock_executor.assert_called_once()
        kwargs = mock_executor.call_args[1]

        # THE KEY TEST: Verify the instructions contain the conversation history
        instructions = kwargs.get("instructions", "")
        assert "Hello" in instructions, "Conversation history not found in instructions"
        assert "Summarize the following conversation" in instructions

    async def test_describe_session_includes_context_parameter(
        self, populated_session_db, mocker
    ):
        """Test that describe_session includes the required context parameter."""
        from mcp_the_force.local_services.describe_session import DescribeSessionService

        # Mock get_summary to return None
        mock_get_summary = mocker.patch(
            "mcp_the_force.unified_session_cache.UnifiedSessionCache.get_summary"
        )
        mock_get_summary.return_value = None

        # Spy on executor
        mock_executor = mocker.patch("mcp_the_force.tools.executor.executor.execute")
        mock_executor.return_value = "Summary"

        service = DescribeSessionService()
        await service.execute(session_id="test-session-1")

        # Verify executor was called with context parameter
        mock_executor.assert_called_once()
        kwargs = mock_executor.call_args[1]

        # THE KEY TEST: Verify context parameter exists
        assert "context" in kwargs, "Missing required parameter: context"
        assert isinstance(kwargs["context"], list), "Context should be a list"
