"""
Unit Tests: SessionBridge CRUD operations.

Tests session mapping logic in isolation (using in-memory SQLite).
"""

import pytest


class TestSessionBridgeCRUD:
    """Unit tests for SessionBridge CRUD operations."""

    @pytest.mark.asyncio
    async def test_store_creates_new_mapping(self):
        """
        Store creates a new mapping in the database.

        Given: No existing mapping
        When: store_cli_session_id is called
        Then: Mapping is created
        """
        from mcp_the_force.cli_agents.session_bridge import SessionBridge

        bridge = SessionBridge(db_path=":memory:")

        await bridge.store_cli_session_id(
            project="test",
            session_id="sess-1",
            cli_name="claude",
            cli_session_id="cli-123",
        )

        result = await bridge.get_cli_session_id("test", "sess-1", "claude")
        assert result == "cli-123"

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self):
        """
        Get returns None for missing mapping.

        Given: No mapping exists
        When: get_cli_session_id is called
        Then: Returns None (not raises)
        """
        from mcp_the_force.cli_agents.session_bridge import SessionBridge

        bridge = SessionBridge(db_path=":memory:")

        result = await bridge.get_cli_session_id("test", "nonexistent", "claude")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_updates_existing_mapping(self):
        """
        Store updates existing mapping (upsert behavior).

        Given: An existing mapping
        When: store_cli_session_id is called with same key
        Then: Mapping is updated
        """
        from mcp_the_force.cli_agents.session_bridge import SessionBridge

        bridge = SessionBridge(db_path=":memory:")

        # Create initial mapping
        await bridge.store_cli_session_id("test", "sess-1", "claude", "old-id")

        # Update mapping
        await bridge.store_cli_session_id("test", "sess-1", "claude", "new-id")

        result = await bridge.get_cli_session_id("test", "sess-1", "claude")
        assert result == "new-id"

    @pytest.mark.asyncio
    async def test_different_clis_independent(self):
        """
        Different CLIs maintain independent mappings.

        Given: Same project and session_id
        When: Different CLIs store mappings
        Then: Each CLI has its own mapping
        """
        from mcp_the_force.cli_agents.session_bridge import SessionBridge

        bridge = SessionBridge(db_path=":memory:")

        await bridge.store_cli_session_id("test", "sess-1", "claude", "claude-id")
        await bridge.store_cli_session_id("test", "sess-1", "gemini", "gemini-id")

        assert (
            await bridge.get_cli_session_id("test", "sess-1", "claude") == "claude-id"
        )
        assert (
            await bridge.get_cli_session_id("test", "sess-1", "gemini") == "gemini-id"
        )

    @pytest.mark.asyncio
    async def test_different_projects_independent(self):
        """
        Different projects maintain independent mappings.

        Given: Same session_id and CLI
        When: Different projects store mappings
        Then: Each project has its own mapping
        """
        from mcp_the_force.cli_agents.session_bridge import SessionBridge

        bridge = SessionBridge(db_path=":memory:")

        await bridge.store_cli_session_id("proj-a", "sess-1", "claude", "id-a")
        await bridge.store_cli_session_id("proj-b", "sess-1", "claude", "id-b")

        assert await bridge.get_cli_session_id("proj-a", "sess-1", "claude") == "id-a"
        assert await bridge.get_cli_session_id("proj-b", "sess-1", "claude") == "id-b"


class TestSessionBridgeDataclass:
    """Unit tests for SessionMapping dataclass."""

    def test_session_mapping_creation(self):
        """SessionMapping can be created with required fields."""
        from mcp_the_force.cli_agents.session_bridge import SessionMapping

        mapping = SessionMapping(
            project="test-project",
            session_id="user-session",
            cli_name="claude",
            cli_session_id="abc-123",
        )

        assert mapping.project == "test-project"
        assert mapping.session_id == "user-session"
        assert mapping.cli_name == "claude"
        assert mapping.cli_session_id == "abc-123"
