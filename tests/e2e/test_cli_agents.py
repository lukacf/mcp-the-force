"""
E2E Tests for CLI Agents.

Phase 1: Real tests that define expected system behavior.
Tests FAIL because code is not implemented yet (not because tests are stubs).

Gate: 1 (red is OK, but must be executable - no boot failures)

Requirements covered:
- REQ-1.1.x: work_with tool behavior
- REQ-1.2.x: consult_with tool behavior
- REQ-3.x: Session management
- REQ-3.3.x: Cross-tool flow
"""

import pytest


# =============================================================================
# Scenario 1: Single task with model → response has session metadata
# =============================================================================


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_work_with_anthropic_model_returns_response():
    """
    REQ-1.1.1, REQ-1.1.2, REQ-1.1.3

    Given: A user calls work_with(agent="claude-sonnet-4-5", task="say hello")
    When: The model resolves to Claude CLI and executes
    Then: Response contains content from Claude
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("work_with")
    assert metadata is not None, "work_with not found in TOOL_REGISTRY"

    # Execute the tool - agent is model name, resolves to Claude CLI
    result = await execute(
        metadata,
        agent="claude-sonnet-4-5",
        task="Say hello",
        session_id="e2e-test-claude-1",
        role="default",
    )

    assert result is not None
    assert len(result) > 0


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_work_with_google_model_returns_response():
    """
    REQ-1.1.1, REQ-1.1.2, REQ-1.1.3

    Given: A user calls work_with(agent="gemini-3-flash-preview", task="say hello")
    When: The model resolves to Gemini CLI and executes
    Then: Response contains content from Gemini
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("work_with")
    assert metadata is not None, "work_with not found in TOOL_REGISTRY"

    result = await execute(
        metadata,
        agent="gemini-3-flash-preview",
        task="Say hello",
        session_id="e2e-test-gemini-1",
        role="default",
    )

    assert result is not None
    assert len(result) > 0


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_work_with_anthropic_model_stores_session_mapping(isolate_test_databases):
    """
    REQ-3.1.1

    Given: A work_with call with Anthropic model completes
    When: The CLI returns a session_id
    Then: The mapping is stored in SessionBridge under CLI name "claude"
    """
    from mcp_the_force.cli_agents.session_bridge import SessionBridge
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("work_with")
    assert metadata is not None, "work_with not found in TOOL_REGISTRY"

    await execute(
        metadata,
        agent="claude-sonnet-4-5",
        task="Remember this",
        session_id="e2e-test-mapping",
        role="default",
    )

    # Verify session bridge has the mapping (stored under CLI name, not model name)
    bridge = SessionBridge()
    cli_session_id = await bridge.get_cli_session_id(
        project="mcp-the-force",
        session_id="e2e-test-mapping",
        cli_name="claude",
    )

    assert cli_session_id is not None


# =============================================================================
# Scenario 2: Resume same CLI → --resume flag used
# =============================================================================


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_resume_same_cli_uses_resume_flag(isolate_test_databases):
    """
    REQ-3.3.1

    Given: A session already has a Claude CLI session mapping
    When: work_with is called again with same model (same CLI)
    Then: The CLI is invoked with --resume <cli_session_id>
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("work_with")
    assert metadata is not None, "work_with not found in TOOL_REGISTRY"

    # Turn 1: Create session with Anthropic model (resolves to Claude CLI)
    await execute(
        metadata,
        agent="claude-sonnet-4-5",
        task="Remember the number 42",
        session_id="e2e-resume-test",
        role="default",
    )

    # Turn 2: Resume with same model - should use --resume flag
    result = await execute(
        metadata,
        agent="claude-sonnet-4-5",
        task="What number did I ask you to remember?",
        session_id="e2e-resume-test",
        role="default",
    )

    # The response should reference 42 (proving context was preserved)
    assert "42" in result


# =============================================================================
# Scenario 3: Cross-CLI handoff → context injected
# =============================================================================


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_cross_cli_handoff_injects_context(isolate_test_databases):
    """
    REQ-3.3.2

    Given: A session has history from Claude CLI (Anthropic model)
    When: work_with is called with Google model (Gemini CLI) on same session
    Then: Claude's history is compacted and injected as context
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("work_with")
    assert metadata is not None, "work_with not found in TOOL_REGISTRY"

    # Turn 1: Work with Anthropic model (resolves to Claude CLI)
    await execute(
        metadata,
        agent="claude-sonnet-4-5",
        task="The secret code is ALPHA-BRAVO-CHARLIE",
        session_id="e2e-handoff-test",
        role="default",
    )

    # Turn 2: Hand off to Google model (resolves to Gemini CLI)
    result = await execute(
        metadata,
        agent="gemini-3-flash-preview",
        task="What was the secret code mentioned earlier?",
        session_id="e2e-handoff-test",
        role="default",
    )

    # Gemini should know the code from injected context
    assert "ALPHA" in result or "BRAVO" in result or "CHARLIE" in result


# =============================================================================
# Scenario 4: API→CLI handoff → history compacted
# =============================================================================


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_api_to_cli_handoff_compacts_history(isolate_test_databases):
    """
    REQ-3.2.1

    Given: A session has history from consult_with (API model)
    When: work_with is called on the same session
    Then: API history is compacted and injected into CLI task
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    consult_metadata = get_tool("consult_with")
    assert consult_metadata is not None, "consult_with not found in TOOL_REGISTRY"
    work_metadata = get_tool("work_with")
    assert work_metadata is not None, "work_with not found in TOOL_REGISTRY"

    # Turn 1: Consult with API model (uses same model vocabulary)
    await execute(
        consult_metadata,
        model="gpt-5.2",
        question="The project name is PHOENIX. Remember it.",
        session_id="e2e-api-cli-handoff",
        output_format="plain text",
    )

    # Turn 2: Work with CLI agent - should receive compacted API history
    result = await execute(
        work_metadata,
        agent="claude-sonnet-4-5",
        task="What project name was mentioned?",
        session_id="e2e-api-cli-handoff",
        role="default",
    )

    assert "PHOENIX" in result


# =============================================================================
# Scenario 5: consult_with multi-turn → session continuity
# =============================================================================


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_consult_with_routes_to_model(isolate_test_databases):
    """
    REQ-1.2.1, REQ-1.2.2

    Given: A user calls consult_with(model="gpt-5.2", question="hello")
    When: The tool executes
    Then: It routes to chat_with_gpt52 internally and returns a response
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("consult_with")
    assert metadata is not None, "consult_with not found in TOOL_REGISTRY"

    result = await execute(
        metadata,
        model="gpt-5.2",
        question="What is 2+2?",
        session_id="e2e-consult-test",
        output_format="plain text",
    )

    assert result is not None
    assert len(result) > 0


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_consult_with_multi_turn_preserves_session(isolate_test_databases):
    """
    REQ-1.2.1

    Given: Two consult_with calls with the same session_id
    When: The second call executes
    Then: The model has context from the first call
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("consult_with")
    assert metadata is not None, "consult_with not found in TOOL_REGISTRY"

    # Turn 1
    await execute(
        metadata,
        model="gpt-5.2",
        question="Remember this number: 999",
        session_id="e2e-consult-multi",
        output_format="plain text",
    )

    # Turn 2
    result = await execute(
        metadata,
        model="gpt-5.2",
        question="What number did I ask you to remember?",
        session_id="e2e-consult-multi",
        output_format="plain text",
    )

    assert "999" in result


# =============================================================================
# Scenario 6: Single task with OpenAI model (Codex CLI) → response has session metadata
# =============================================================================


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_work_with_openai_model_returns_response():
    """
    REQ-1.1.1, REQ-1.1.2, REQ-1.1.3

    Given: A user calls work_with(agent="gpt-5.2", task="say hello")
    When: The model resolves to Codex CLI and executes
    Then: Response contains content from Codex
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("work_with")
    assert metadata is not None, "work_with not found in TOOL_REGISTRY"

    result = await execute(
        metadata,
        agent="gpt-5.2",
        task="Say hello",
        session_id="e2e-test-codex-1",
        role="default",
    )

    assert result is not None
    assert len(result) > 0


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_work_with_openai_model_stores_thread_mapping(isolate_test_databases):
    """
    REQ-3.1.1

    Given: A work_with call with OpenAI model (Codex CLI) completes
    When: The CLI returns a thread_id
    Then: The mapping is stored in SessionBridge under CLI name "codex"
    """
    from mcp_the_force.cli_agents.session_bridge import SessionBridge
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("work_with")
    assert metadata is not None, "work_with not found in TOOL_REGISTRY"

    await execute(
        metadata,
        agent="gpt-5.2",
        task="Remember this",
        session_id="e2e-test-codex-mapping",
        role="default",
    )

    # Verify session bridge has the mapping (stored under CLI name, not model name)
    bridge = SessionBridge()
    cli_session_id = await bridge.get_cli_session_id(
        project="mcp-the-force",
        session_id="e2e-test-codex-mapping",
        cli_name="codex",
    )

    assert cli_session_id is not None


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_codex_resume_uses_exec_resume_command(isolate_test_databases):
    """
    REQ-3.3.1 (Codex variant)

    Given: A session already has a Codex thread mapping (via OpenAI model)
    When: work_with is called again with the same session_id
    Then: The CLI is invoked with 'exec resume <thread_id>' (not --resume)

    NOTE: This validates the Codex-specific resume pattern from RCT.
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("work_with")
    assert metadata is not None, "work_with not found in TOOL_REGISTRY"

    # Turn 1: Create session with OpenAI model (resolves to Codex CLI)
    await execute(
        metadata,
        agent="gpt-5.2",
        task="Remember the number 99",
        session_id="e2e-codex-resume-test",
        role="default",
    )

    # Turn 2: Resume - should use 'exec resume <thread_id>' command
    result = await execute(
        metadata,
        agent="gpt-5.2",
        task="What number did I ask you to remember?",
        session_id="e2e-codex-resume-test",
        role="default",
    )

    # The response should reference 99 (proving context was preserved via resume)
    assert "99" in result


# =============================================================================
# Meta test - verifies test file loads
# =============================================================================


def test_e2e_tests_load():
    """This test passes to confirm the test file loads without import errors."""
    assert True


@pytest.mark.e2e
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_work_with_can_access_project_files():
    """
    E2E validation that CLI agents can actually access files in project directory.

    CRITICAL: This tests the REAL behavior, not just command format.
    If this fails, --add-dir is not working in practice.

    Given: A project directory with a test file
    When: work_with is called with that project
    Then: The CLI agent can read and report the file contents
    """
    import tempfile
    import os
    from pathlib import Path
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import executor

    # Create temp directory with test file
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_readme.txt"
        test_content = "This is a test file for E2E validation. Magic string: XYZ123ABC"
        test_file.write_text(test_content)

        metadata = get_tool("work_with")
        assert metadata is not None

        # Call work_with, asking agent to read the file
        result = await executor.execute(
            metadata,
            agent="claude-sonnet-4-5",
            task="Read the file test_readme.txt in this directory and tell me what magic string it contains. Just output the magic string, nothing else.",
            session_id=f"e2e-file-access-test-{os.getpid()}",
            project_dir=tmpdir,  # This should be passed to CLIAgentService
        )

        # Verify the agent could access and read the file
        assert result is not None, "Should get response from agent"
        assert "XYZ123ABC" in result, (
            f"Agent should have read the magic string from the file. "
            f"Got response: {result[:500]}"
        )
