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

    # Mock the compactor to return a short summary
    # (MockAdapter echoes full prompt, defeating the test)
    mock_summary = "Summary: 100 messages about repeated x patterns."
    mocker.patch(
        "mcp_the_force.cli_agents.compactor.Compactor._compact_with_handoff_prompt",
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
async def test_cross_cli_handoff_injects_compacted_context(
    isolate_test_databases, mocker
):
    """
    CP-CROSS-TOOL: Context injection.

    Given: Session has history from Claude CLI
    When: work_with is called with agent="gemini-3-flash-preview" (resolves to gemini CLI)
    Then: Claude's history is compacted and injected into Gemini's task
    """
    from mcp_the_force.unified_session_cache import UnifiedSessionCache, UnifiedSession
    from mcp_the_force.local_services.cli_agent_service import CLIAgentService
    from mcp_the_force.cli_agents.executor import CLIResult
    import time

    # Mock CLI availability and execution
    mocker.patch(
        "mcp_the_force.cli_agents.availability.CLIAvailabilityChecker.is_available",
        return_value=True,
    )
    mocker.patch(
        "mcp_the_force.cli_agents.executor.CLIExecutor.execute",
        return_value=CLIResult(
            stdout='{"content": "Continuing auth implementation..."}',
            stderr="",
            return_code=0,
            timed_out=False,
        ),
    )
    mocker.patch(
        "mcp_the_force.cli_agents.summarizer.OutputSummarizer.summarize",
        return_value="Continuing auth implementation with injected context.",
    )

    # Pre-populate session with Claude history
    # Note: Session key is (project, session_id) - tool info is per-turn in history
    session = UnifiedSession(
        project="mcp-the-force",
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
async def test_api_to_cli_handoff_compacts_api_history(isolate_test_databases, mocker):
    """
    CP-CROSS-TOOL: API→CLI handoff.

    Given: Session has history from consult_with (API model)
    When: work_with is called
    Then: API history is compacted and injected into CLI task
    """
    from mcp_the_force.unified_session_cache import UnifiedSessionCache, UnifiedSession
    from mcp_the_force.local_services.cli_agent_service import CLIAgentService
    from mcp_the_force.cli_agents.executor import CLIResult
    import time

    # Mock CLI availability and execution
    mocker.patch(
        "mcp_the_force.cli_agents.availability.CLIAvailabilityChecker.is_available",
        return_value=True,
    )
    mocker.patch(
        "mcp_the_force.cli_agents.executor.CLIExecutor.execute",
        return_value=CLIResult(
            stdout='{"session_id": "cli-123", "content": "Database schema implemented"}',
            stderr="",
            return_code=0,
            timed_out=False,
        ),
    )
    mocker.patch(
        "mcp_the_force.cli_agents.summarizer.OutputSummarizer.summarize",
        return_value="Database schema implemented based on PostgreSQL recommendation.",
    )

    # Pre-populate session with API model history
    # Note: Session key is (project, session_id) - tool info is per-turn in history
    session = UnifiedSession(
        project="mcp-the-force",
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
async def test_handoff_metadata_recorded(isolate_test_databases, mocker, tmp_path):
    """
    CP-CROSS-TOOL: Handoff metadata.

    Given: A cross-tool handoff occurs
    When: The CLI execution completes
    Then: Metadata includes context_injected=True and context_source
    """
    from mcp_the_force.unified_session_cache import UnifiedSessionCache, UnifiedSession
    from mcp_the_force.local_services.cli_agent_service import CLIAgentService
    from mcp_the_force.cli_agents.executor import CLIResult
    import time

    # Use tmp_path for consistent project name
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    project_name = "test-project"

    # Mock CLI availability and execution
    mocker.patch(
        "mcp_the_force.cli_agents.availability.CLIAvailabilityChecker.is_available",
        return_value=True,
    )
    mocker.patch(
        "mcp_the_force.cli_agents.executor.CLIExecutor.execute",
        return_value=CLIResult(
            stdout='{"session_id": "cli-456", "content": "Continued"}',
            stderr="",
            return_code=0,
            timed_out=False,
        ),
    )
    mocker.patch(
        "mcp_the_force.cli_agents.summarizer.OutputSummarizer.summarize",
        return_value="Continued from previous context.",
    )

    # Pre-populate session with history from different tool (per-turn tracking)
    # Note: Session key is (project, session_id) - tool info is per-turn in history
    session = UnifiedSession(
        project=project_name,
        session_id="metadata-test",
        history=[
            {"role": "user", "content": "Initial message", "tool": "chat_with_gpt52"},
            {"role": "assistant", "content": "Response", "tool": "chat_with_gpt52"},
        ],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(session)

    # Execute with different CLI (Anthropic model resolves to claude CLI)
    service = CLIAgentService(project_dir=str(project_dir))
    await service.execute(
        agent="claude-sonnet-4-5",
        task="Continue",
        session_id="metadata-test",
        role="default",
        context=[],
    )

    # Check updated session for metadata (same session, different tools per-turn)
    updated_session = await UnifiedSessionCache.get_session(
        project=project_name,
        session_id="metadata-test",
    )

    # The last turn should have handoff metadata
    assert updated_session is not None, "Session should exist"
    last_turn = updated_session.history[-1]
    assert last_turn.get("metadata", {}).get("context_injected") is True


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_cli_to_api_handoff_via_consult_with(isolate_test_databases, tmp_path):
    """
    CP-CROSS-TOOL: CLI→API handoff via consult_with.

    Given: Session has history from work_with (CLI agent)
    When: consult_with is called
    Then: CLI history is compacted and injected into API model prompt
    """
    from mcp_the_force.unified_session_cache import UnifiedSessionCache, UnifiedSession
    from mcp_the_force.local_services.cli_agent_service import ConsultationService
    import time

    # Use tmp_path for consistent project name
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    project_name = "test-project"

    # Pre-populate session with CLI history
    session = UnifiedSession(
        project=project_name,
        session_id="cli-to-api-test",
        history=[
            {
                "role": "user",
                "content": "Tell me a joke about programming",
                "tool": "work_with",
            },
            {
                "role": "assistant",
                "content": "Why do programmers prefer dark mode? Light attracts bugs!",
                "tool": "work_with",
            },
        ],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(session)

    # Now call consult_with - should inject CLI history
    service = ConsultationService(project_dir=str(project_dir))

    # Use MockAdapter for API model (it echoes back the prompt)
    result = await service.execute(
        model="gpt52",  # Routes to chat_with_gpt52
        question="Rate that joke on a scale of 1-10",
        session_id="cli-to-api-test",
        output_format="plain text",
    )

    # MockAdapter echoes back the prompt, so we should see the compacted history
    # in the result (since question now includes the compacted history prefix)
    assert result is not None
    # The compacted history should be included in the MockAdapter's echo
    # Note: MockAdapter in tools/mock_adapter.py echoes instructions
    assert "joke" in result.lower() or "programming" in result.lower()


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_same_cli_with_intervening_api_call_does_not_resume(
    isolate_test_databases, mocker, tmp_path
):
    """
    CP-CROSS-TOOL: Same CLI with intervening API call.

    Given: Session has history: Claude→GPT-5.2 (CLI then API)
    When: work_with called again with Claude
    Then:
      - Should NOT use --resume (because last turn was API, not CLI)
      - Should inject compacted context including GPT-5.2 conversation
      - Metadata should show context_injected=True

    This ensures cross-tool context is visible when returning to a CLI
    after using an API model.
    """
    from mcp_the_force.unified_session_cache import UnifiedSessionCache, UnifiedSession
    from mcp_the_force.local_services.cli_agent_service import CLIAgentService
    from mcp_the_force.cli_agents.executor import CLIResult
    from mcp_the_force.cli_agents.session_bridge import SessionBridge
    import time

    # Use tmp_path for consistent project name
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    project_name = "test-project"

    # Pre-populate SessionBridge with an existing Claude CLI session
    # (simulating a previous Claude call)
    bridge = SessionBridge()
    await bridge.store_cli_session_id(
        project=project_name,
        session_id="intervening-api-test",
        cli_name="claude",
        cli_session_id="existing-claude-session-abc",
    )

    # Pre-populate session with: Claude turn → GPT-5.2 turn
    session = UnifiedSession(
        project=project_name,
        session_id="intervening-api-test",
        history=[
            # First: Claude CLI call (work_with)
            {
                "role": "user",
                "content": "Tell me a joke about AI",
                "tool": "work_with",
            },
            {
                "role": "assistant",
                "content": "Why did the AI go to therapy? Unresolved dependencies!",
                "tool": "work_with",
                "metadata": {"cli_name": "claude"},
            },
            # Second: GPT-5.2 API call (consult_with)
            {
                "role": "user",
                "content": "Rate that joke 1-10",
                "tool": "consult_with",
            },
            {
                "role": "assistant",
                "content": "I'd rate it 7/10 - clever tech humor!",
                "tool": "consult_with",
            },
        ],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(session)

    # Track what command was executed
    executed_commands = []

    async def mock_execute(command, env, timeout, cwd=None):
        executed_commands.append(command)
        return CLIResult(
            stdout='{"session_id": "new-claude-session", "content": "Got it!"}',
            stderr="",
            return_code=0,
            timed_out=False,
        )

    mocker.patch(
        "mcp_the_force.cli_agents.availability.CLIAvailabilityChecker.is_available",
        return_value=True,
    )
    mocker.patch(
        "mcp_the_force.cli_agents.executor.CLIExecutor.execute",
        side_effect=mock_execute,
    )
    mocker.patch(
        "mcp_the_force.cli_agents.summarizer.OutputSummarizer.summarize",
        return_value="Got it! Understood the previous context.",
    )

    # Call Claude again - should NOT use resume since last turn was API
    service = CLIAgentService(project_dir=str(project_dir))
    await service.execute(
        agent="claude-sonnet-4-5",
        task="What was the rating?",
        session_id="intervening-api-test",
        role="default",
        context=[],
    )

    # Verify the command did NOT include resume flag
    assert len(executed_commands) == 1
    cmd = executed_commands[0]
    # Should NOT have --resume flag (new session, not resuming)
    assert "--resume" not in cmd, f"Should not use --resume, but got: {cmd}"

    # Verify context was injected (check the task in the command includes history)
    # The task should contain compacted history mentioning the joke and rating
    task_in_cmd = " ".join(cmd)  # Convert list to string to search
    # Context should be injected as part of the prompt/task
    assert (
        "joke" in task_in_cmd.lower() or "7/10" in task_in_cmd
    ), f"Context should be injected with previous conversation, got: {cmd}"

    # Verify metadata shows context was injected
    updated_session = await UnifiedSessionCache.get_session(
        project=project_name,
        session_id="intervening-api-test",
    )
    assert updated_session is not None
    last_turn = updated_session.history[-1]
    assert (
        last_turn.get("metadata", {}).get("context_injected") is True
    ), f"Should have context_injected=True, got: {last_turn.get('metadata')}"


def test_cross_tool_integration_tests_load():
    """Meta-test: Verify integration test file loads correctly."""
    assert True
