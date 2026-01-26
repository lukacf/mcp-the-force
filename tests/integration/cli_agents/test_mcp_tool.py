"""
Integration Tests: MCP tool ↔ LocalService ↔ session cache flow.

Choke Point: CP-MCP-WIRING
Phase 1: Real tests that fail because code not implemented yet.
"""

import pytest


@pytest.mark.integration
@pytest.mark.cli_agents
def test_work_with_registered_in_tool_registry():
    """
    CP-MCP-WIRING: Tool registration.

    Given: The MCP server module is imported
    When: TOOL_REGISTRY is populated (via get_tool to trigger lazy load)
    Then: work_with is registered with correct metadata
    """
    from mcp_the_force.tools.registry import get_tool

    metadata = get_tool("work_with")
    assert metadata is not None, "work_with not found in TOOL_REGISTRY"

    # LocalService pattern: service_cls is set on spec_class, adapter_class is None
    spec_class = metadata.spec_class
    assert getattr(spec_class, "service_cls", None) is not None
    assert getattr(spec_class, "adapter_class", None) is None


@pytest.mark.integration
@pytest.mark.cli_agents
def test_consult_with_registered_in_tool_registry():
    """
    CP-MCP-WIRING: Tool registration.

    Given: The MCP server module is imported
    When: TOOL_REGISTRY is populated (via get_tool to trigger lazy load)
    Then: consult_with is registered with correct metadata
    """
    from mcp_the_force.tools.registry import get_tool

    metadata = get_tool("consult_with")
    assert metadata is not None, "consult_with not found in TOOL_REGISTRY"

    # LocalService pattern
    spec_class = metadata.spec_class
    assert getattr(spec_class, "service_cls", None) is not None
    assert getattr(spec_class, "adapter_class", None) is None


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_work_with_dispatches_to_cli_agent_service():
    """
    CP-MCP-WIRING: LocalService dispatch.

    Given: A work_with call via executor with model name
    When: The executor routes the call (model→CLI resolution)
    Then: CLIAgentService.execute() is invoked and returns a result
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("work_with")
    assert metadata is not None, "work_with not found in TOOL_REGISTRY"

    # This should dispatch to CLIAgentService
    # Model name resolves to CLI via model registry
    result = await execute(
        metadata,
        agent="claude-sonnet-4-5",
        task="Test dispatch",
        session_id="dispatch-test",
        role="default",
    )

    assert result is not None


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_consult_with_routes_to_internal_chat_tool():
    """
    CP-MCP-WIRING: Internal routing.

    Given: consult_with(model="gpt-5.2", ...)
    When: ConsultationService resolves the model
    Then: It routes to chat_with_gpt52 via executor
    """
    from mcp_the_force.tools.registry import get_tool
    from mcp_the_force.tools.executor import execute

    metadata = get_tool("consult_with")
    assert metadata is not None, "consult_with not found in TOOL_REGISTRY"

    # This should route to chat_with_gpt52 internally
    result = await execute(
        metadata,
        model="gpt-5.2",
        question="Test routing",
        session_id="route-test",
        output_format="plain text",
    )

    assert result is not None


@pytest.mark.integration
@pytest.mark.cli_agents
def test_chat_with_tools_not_exposed_via_mcp():
    """
    CP-MCP-WIRING: MCP visibility.

    Given: chat_with_* tools marked as internal_only
    When: We check their visibility flag
    Then: internal_only is True (meaning they won't be exposed via MCP)
    """
    from mcp_the_force.tools.registry import get_tool, list_tools

    # Trigger lazy population
    tools = list_tools()

    # chat_with_gpt52 should exist but be internal_only
    assert "chat_with_gpt52" in tools

    metadata = get_tool("chat_with_gpt52")
    assert metadata is not None
    assert getattr(metadata.spec_class, "internal_only", False) is True


@pytest.mark.integration
@pytest.mark.cli_agents
def test_chat_with_tools_still_in_registry_for_routing():
    """
    CP-MCP-WIRING: Internal availability.

    Given: chat_with_* tools marked as internal_only
    When: TOOL_REGISTRY is checked
    Then: chat_with_* tools ARE present (for consult_with routing)
    """
    from mcp_the_force.tools.registry import list_tools

    # Trigger lazy population and get all tools
    tools = list_tools()

    # These should all be in registry for internal routing
    internal_tools = [
        "chat_with_gpt52",
        "chat_with_gpt52_pro",
        "chat_with_gemini3_pro_preview",
        "chat_with_grok41",
    ]

    for tool_name in internal_tools:
        assert tool_name in tools, f"{tool_name} should be in TOOL_REGISTRY"


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_work_with_stores_turn_in_session_cache(
    isolate_test_databases, mocker, tmp_path
):
    """
    CP-MCP-WIRING: Session persistence.

    Given: A work_with call completes
    When: The response is returned
    Then: The turn is stored in UnifiedSessionCache
    """
    from mcp_the_force.unified_session_cache import UnifiedSessionCache
    from mcp_the_force.local_services.cli_agent_service import CLIAgentService
    from mcp_the_force.cli_agents.executor import CLIResult

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
            # Claude CLI output format: {"type": "result", "session_id": "...", "result": "..."}
            stdout='{"type": "result", "session_id": "cli-789", "result": "Done"}',
            stderr="",
            return_code=0,
            timed_out=False,
        ),
    )
    mocker.patch(
        "mcp_the_force.cli_agents.summarizer.OutputSummarizer.summarize",
        return_value="Task completed.",
    )

    service = CLIAgentService(project_dir=str(project_dir))
    await service.execute(
        agent="claude-sonnet-4-5",
        task="Store this turn",
        session_id="cache-test-session",
        role="default",
    )

    # Verify turn was stored in session cache
    # Note: Session key is now (project, session_id) - no tool in key
    session = await UnifiedSessionCache.get_session(
        project=project_name,
        session_id="cache-test-session",
    )

    assert session is not None
    assert len(session.history) > 0
    # Verify the turn has work_with tool attribution
    assert session.history[-1].get("tool") == "work_with"


def test_mcp_tool_integration_tests_load():
    """Meta-test: Verify integration test file loads correctly."""
    assert True
