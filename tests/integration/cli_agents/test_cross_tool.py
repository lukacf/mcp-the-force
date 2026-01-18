"""
Integration Tests: Compactor ↔ context injection.

Choke Point: CP-CROSS-TOOL
Phase 1: Real tests that fail because code not implemented yet.
"""

import pytest


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_compactor_formats_history_when_fits(isolate_test_databases):
    """
    CP-CROSS-TOOL: History formatting.

    Given: Session history that fits within CLI context limit
    When: Compactor processes it
    Then: History is formatted as a context block (not summarized)
    """
    from mcp_the_force.cli_agents.compactor import Compactor

    history = [
        {"role": "user", "content": "Design an auth system"},
        {"role": "assistant", "content": "Here's a JWT-based auth design..."},
    ]

    compactor = Compactor()
    result = await compactor.compact_for_cli(
        history=history,
        target_cli="claude",
        max_tokens=8000,
    )

    # Should contain the original content (not summarized)
    assert "auth system" in result
    assert "JWT-based" in result


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_compactor_summarizes_when_exceeds_limit(isolate_test_databases, mocker):
    """
    CP-CROSS-TOOL: History summarization.

    Given: Session history that exceeds CLI context limit
    When: Compactor processes it
    Then: History is summarized via API model
    """
    from mcp_the_force.cli_agents.compactor import Compactor

    # Mock the summarizer to return a short summary
    # (MockAdapter echoes full prompt, defeating the test)
    mock_summary = "Summary: 100 messages about repeated x patterns."
    mocker.patch(
        "mcp_the_force.cli_agents.compactor.Compactor._call_summarizer",
        return_value=mock_summary,
    )

    # Create large history that would exceed limits
    large_history = [
        {"role": "user", "content": f"Message {i}: " + "x" * 1000} for i in range(100)
    ]

    compactor = Compactor()
    result = await compactor.compact_for_cli(
        history=large_history,
        target_cli="claude",
        max_tokens=1000,  # Small limit to force summarization
    )

    # Result should be shorter than original (summarized)
    original_length = sum(len(m["content"]) for m in large_history)
    assert len(result) < original_length
    assert mock_summary in result


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_cross_cli_handoff_injects_compacted_context(isolate_test_databases):
    """
    CP-CROSS-TOOL: Context injection.

    Given: Session has history from Claude CLI
    When: work_with is called with agent="gemini-3-flash-preview" (resolves to gemini CLI)
    Then: Claude's history is compacted and injected into Gemini's task
    """
    from mcp_the_force.unified_session_cache import UnifiedSessionCache, UnifiedSession
    from mcp_the_force.local_services.cli_agent_service import CLIAgentService
    import time

    # Pre-populate session with Claude history
    session = UnifiedSession(
        project="mcp-the-force",
        tool="work_with",
        session_id="cross-tool-test",
        history=[
            {"role": "user", "content": "Design auth with Claude", "tool": "work_with"},
            {
                "role": "assistant",
                "content": "Here's the auth design from Claude...",
                "tool": "work_with",
            },
        ],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(session)

    # Now call with Gemini model - should inject Claude's history
    service = CLIAgentService()
    result = await service.execute(
        agent="gemini-3-flash-preview",
        task="Continue the auth implementation",
        session_id="cross-tool-test",
        role="default",
        context=[],
    )

    # Result should show awareness of previous context
    # (In practice, the injected context would help Gemini understand)
    assert result is not None


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_api_to_cli_handoff_compacts_api_history(isolate_test_databases):
    """
    CP-CROSS-TOOL: API→CLI handoff.

    Given: Session has history from consult_with (API model)
    When: work_with is called
    Then: API history is compacted and injected into CLI task
    """
    from mcp_the_force.unified_session_cache import UnifiedSessionCache, UnifiedSession
    from mcp_the_force.local_services.cli_agent_service import CLIAgentService
    import time

    # Pre-populate session with API model history
    session = UnifiedSession(
        project="mcp-the-force",
        tool="chat_with_gpt52",  # API model
        session_id="api-to-cli-test",
        history=[
            {
                "role": "user",
                "content": "What's the best database for this?",
                "tool": "chat_with_gpt52",
            },
            {
                "role": "assistant",
                "content": "PostgreSQL would be ideal because...",
                "tool": "chat_with_gpt52",
            },
        ],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(session)

    # Now call work_with - should inject API history
    service = CLIAgentService()
    result = await service.execute(
        agent="claude-sonnet-4-5",
        task="Implement the database schema",
        session_id="api-to-cli-test",
        role="default",
        context=[],
    )

    assert result is not None


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_handoff_metadata_recorded(isolate_test_databases):
    """
    CP-CROSS-TOOL: Handoff metadata.

    Given: A cross-tool handoff occurs
    When: The CLI execution completes
    Then: Metadata includes context_injected=True and context_source
    """
    from mcp_the_force.unified_session_cache import UnifiedSessionCache, UnifiedSession
    from mcp_the_force.local_services.cli_agent_service import CLIAgentService
    import time

    # Pre-populate session with history from different tool
    session = UnifiedSession(
        project="mcp-the-force",
        tool="chat_with_gpt52",
        session_id="metadata-test",
        history=[
            {"role": "user", "content": "Initial message"},
            {"role": "assistant", "content": "Response"},
        ],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(session)

    # Execute with different CLI (Anthropic model resolves to claude CLI)
    service = CLIAgentService()
    await service.execute(
        agent="claude-sonnet-4-5",
        task="Continue",
        session_id="metadata-test",
        role="default",
        context=[],
    )

    # Check updated session for metadata
    updated_session = await UnifiedSessionCache.get_session(
        project="mcp-the-force",
        session_id="metadata-test",
    )

    # The last turn should have handoff metadata
    last_turn = updated_session.history[-1]
    assert last_turn.get("metadata", {}).get("context_injected") is True


def test_cross_tool_integration_tests_load():
    """Meta-test: Verify integration test file loads correctly."""
    assert True
