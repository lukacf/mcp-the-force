"""
Integration Tests: SessionBridge ↔ SQLite mapping persistence.

Choke Point: CP-CLI-SESSION
Phase 1: Real tests that fail because code not implemented yet.
"""

import pytest


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_store_and_retrieve_cli_session_mapping(isolate_test_databases):
    """
    CP-CLI-SESSION: Basic round-trip.

    Given: A CLI session ID from Claude execution
    When: Stored via SessionBridge and retrieved
    Then: The mapping is correctly persisted and returned
    """
    from mcp_the_force.cli_agents.session_bridge import SessionBridge

    bridge = SessionBridge()

    await bridge.store_cli_session_id(
        project="test-project",
        session_id="user-session-123",
        cli_name="claude",
        cli_session_id="abc-def-ghi",
    )

    result = await bridge.get_cli_session_id(
        project="test-project",
        session_id="user-session-123",
        cli_name="claude",
    )

    assert result == "abc-def-ghi"


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_different_clis_have_separate_mappings(isolate_test_databases):
    """
    CP-CLI-SESSION: CLI isolation.

    Given: Same session_id used with different CLIs
    When: Each CLI stores its own session ID
    Then: Mappings are separate per CLI
    """
    from mcp_the_force.cli_agents.session_bridge import SessionBridge

    bridge = SessionBridge()

    await bridge.store_cli_session_id("proj", "sess", "claude", "claude-id-123")
    await bridge.store_cli_session_id("proj", "sess", "gemini", "gemini-id-456")
    await bridge.store_cli_session_id("proj", "sess", "codex", "codex-id-789")

    assert await bridge.get_cli_session_id("proj", "sess", "claude") == "claude-id-123"
    assert await bridge.get_cli_session_id("proj", "sess", "gemini") == "gemini-id-456"
    assert await bridge.get_cli_session_id("proj", "sess", "codex") == "codex-id-789"


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_nonexistent_mapping_returns_none(isolate_test_databases):
    """
    CP-CLI-SESSION: Missing mapping handling.

    Given: No mapping exists for a session
    When: get_cli_session_id is called
    Then: Returns None (not raises)
    """
    from mcp_the_force.cli_agents.session_bridge import SessionBridge

    bridge = SessionBridge()

    result = await bridge.get_cli_session_id("proj", "nonexistent", "claude")

    assert result is None


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_mapping_update_overwrites_previous(isolate_test_databases):
    """
    CP-CLI-SESSION: Mapping update.

    Given: A mapping already exists
    When: A new CLI session ID is stored for the same key
    Then: The mapping is updated (not duplicated)
    """
    from mcp_the_force.cli_agents.session_bridge import SessionBridge

    bridge = SessionBridge()

    # Store initial mapping
    await bridge.store_cli_session_id("proj", "sess", "claude", "old-id")

    # Update mapping
    await bridge.store_cli_session_id("proj", "sess", "claude", "new-id")

    # Should get the new value
    result = await bridge.get_cli_session_id("proj", "sess", "claude")
    assert result == "new-id"


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_session_bridge_persists_across_instances(isolate_test_databases):
    """
    CP-CLI-SESSION: Persistence.

    Given: A mapping stored via one SessionBridge instance
    When: A new SessionBridge instance is created
    Then: The mapping is still retrievable (persisted to SQLite)
    """
    from mcp_the_force.cli_agents.session_bridge import SessionBridge

    # Store with first instance
    bridge1 = SessionBridge()
    await bridge1.store_cli_session_id("proj", "persist-test", "claude", "persisted-id")

    # Retrieve with second instance
    bridge2 = SessionBridge()
    result = await bridge2.get_cli_session_id("proj", "persist-test", "claude")

    assert result == "persisted-id"


def test_session_bridge_integration_tests_load():
    """Meta-test: Verify integration test file loads correctly."""
    assert True
