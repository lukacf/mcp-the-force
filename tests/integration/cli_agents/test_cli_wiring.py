"""
Integration Tests: CLI Agents Internal Wiring

These tests verify that our internal components work together correctly.
We mock CLI subprocess calls but test the real wiring between:
- Model registry → CLI plugin resolution
- CLI plugin → Command building
- Executor → Parser pipeline
- Parser → Session bridge storage
- Session bridge → Unified cache

Each test exercises multiple components and asserts cross-component invariants.
"""

import pytest
from unittest.mock import AsyncMock, patch
import json


# =============================================================================
# Mock CLI Responses - What the real CLIs would return
# =============================================================================

MOCK_CLAUDE_OUTPUT = json.dumps(
    [
        {
            "type": "system",
            "subtype": "init",
            "session_id": "claude-session-abc123",
            "tools": ["Read", "Write"],
        },
        {
            "type": "result",
            "subtype": "success",
            "result": "Task completed successfully",
            "session_id": "claude-session-abc123",
        },
    ]
)

MOCK_GEMINI_OUTPUT = json.dumps(
    {
        "session_id": "gemini-session-xyz789",
        "response": "Task completed successfully",
        "stats": {"tokens": 100},
    }
)

MOCK_CODEX_OUTPUT = """{"type":"thread.started","thread_id":"codex-thread-def456"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Task completed successfully"}}
{"type":"turn.completed"}"""


# =============================================================================
# CP-MODEL-CLI-MAP + CP-CLI-COMMAND: Model → CLI → Command
# =============================================================================


@pytest.mark.integration
@pytest.mark.cli_agents
class TestModelToCLICommandWiring:
    """
    Tests the wiring from model name to CLI command construction.

    Flow: Model Registry → CLI Plugin → Command Builder
    Invariant: Given a model name, the correct CLI command is constructed
    """

    def test_anthropic_model_builds_claude_command(self):
        """
        Given: agent="claude-sonnet-4-5"
        When: CLIAgentService prepares the command
        Then: Command uses 'claude' executable with correct flags
        """
        from mcp_the_force.cli_agents.model_cli_resolver import resolve_model_to_cli
        from mcp_the_force.cli_plugins.registry import get_cli_plugin

        # Step 1: Model resolves to CLI name
        cli_name = resolve_model_to_cli("claude-sonnet-4-5")
        assert cli_name == "claude", "Model should resolve to claude CLI"

        # Step 2: CLI name gets plugin
        plugin = get_cli_plugin(cli_name)
        assert plugin is not None, "Claude plugin should be registered"
        assert plugin.executable == "claude"

        # Step 3: Plugin builds command
        command = plugin.build_new_session_args(
            task="Test task",
            context_dirs=["/tmp/project"],
        )

        # Invariant: Command has required structure
        assert "--print" in command, "Claude needs --print for non-interactive mode"
        assert (
            "--output-format" in command
        ), "Claude needs --output-format for JSON output"
        assert "json" in command, "Output format should be json"
        assert "Test task" in command, "Task should be positional argument"

    def test_google_model_builds_gemini_command(self):
        """
        Given: agent="gemini-3-flash-preview"
        When: CLIAgentService prepares the command
        Then: Command uses 'gemini' executable with correct flags
        """
        from mcp_the_force.cli_agents.model_cli_resolver import resolve_model_to_cli
        from mcp_the_force.cli_plugins.registry import get_cli_plugin

        cli_name = resolve_model_to_cli("gemini-3-flash-preview")
        assert cli_name == "gemini"

        plugin = get_cli_plugin(cli_name)
        command = plugin.build_new_session_args(task="Test task", context_dirs=[])

        assert plugin.executable == "gemini"
        assert "Test task" in command

    def test_openai_model_builds_codex_command(self):
        """
        Given: agent="gpt-5.2"
        When: CLIAgentService prepares the command
        Then: Command uses 'codex' executable with correct flags
        """
        from mcp_the_force.cli_agents.model_cli_resolver import resolve_model_to_cli
        from mcp_the_force.cli_plugins.registry import get_cli_plugin

        cli_name = resolve_model_to_cli("gpt-5.2")
        assert cli_name == "codex"

        plugin = get_cli_plugin(cli_name)
        command = plugin.build_new_session_args(task="Test task", context_dirs=[])

        assert plugin.executable == "codex"
        assert "--json" in command, "Codex needs --json for structured output"

    def test_codex_resume_uses_exec_resume_pattern(self):
        """
        Given: Resuming a codex session
        When: CLIAgentService prepares the resume command
        Then: Command uses 'exec resume <thread_id>' (NOT --resume flag)

        This is a critical difference from Claude/Gemini!
        """
        from mcp_the_force.cli_plugins.registry import get_cli_plugin

        plugin = get_cli_plugin("codex")
        command = plugin.build_resume_args(
            session_id="codex-thread-123",
            task="Continue task",
        )

        # Codex uses 'exec resume <id>' not '--resume <id>'
        assert "exec" in command
        assert "resume" in command
        assert "codex-thread-123" in command
        assert "--resume" not in command  # This would be wrong!


# =============================================================================
# CP-EXECUTOR + CP-PARSER: Execute → Parse → Extract Session
# =============================================================================


@pytest.mark.integration
@pytest.mark.cli_agents
class TestExecutorParserWiring:
    """
    Tests the wiring from CLI execution to parsed response.

    Flow: CLIExecutor → subprocess (mocked) → Parser → ParsedCLIResponse
    Invariant: CLI output is correctly parsed into structured response with session_id
    """

    @pytest.mark.asyncio
    async def test_claude_output_parsed_to_session_id(self):
        """
        Given: Claude CLI returns JSON output
        When: Output flows through parser pipeline
        Then: session_id is extracted and available
        """
        from mcp_the_force.cli_plugins.claude import ClaudePlugin
        from mcp_the_force.cli_agents.executor import CLIExecutor, CLIResult

        # Mock the subprocess call
        mock_result = CLIResult(
            stdout=MOCK_CLAUDE_OUTPUT,
            stderr="",
            return_code=0,
            timed_out=False,
        )

        with patch.object(CLIExecutor, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_result

            executor = CLIExecutor()
            result = await executor.execute(
                command=["claude", "--print", "-p", "test"],
                env={},
                timeout=60,
            )

            # Parse the output
            plugin = ClaudePlugin()
            parsed = plugin.parse_output(result.stdout)

            # Invariant: session_id extracted
            assert parsed.session_id == "claude-session-abc123"
            assert "completed" in parsed.content.lower()

    @pytest.mark.asyncio
    async def test_codex_jsonl_parsed_to_thread_id(self):
        """
        Given: Codex CLI returns JSONL output (multiple lines)
        When: Output flows through parser pipeline
        Then: thread_id is extracted and mapped to session_id
        """
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        plugin = CodexPlugin()
        parsed = plugin.parse_output(MOCK_CODEX_OUTPUT)

        # Invariant: thread_id becomes session_id
        assert parsed.session_id == "codex-thread-def456"
        assert "completed" in parsed.content.lower()


# =============================================================================
# CP-SESSION-BRIDGE: Parser → Session Storage
# =============================================================================


@pytest.mark.integration
@pytest.mark.cli_agents
class TestParserToSessionBridgeWiring:
    """
    Tests the wiring from parsed response to session storage.

    Flow: ParsedCLIResponse → SessionBridge → SQLite
    Invariant: CLI session ID is persisted and retrievable by (project, session_id, cli_name)
    """

    @pytest.mark.asyncio
    async def test_parsed_session_stored_in_bridge(self, isolate_test_databases):
        """
        Given: A parsed CLI response with session_id
        When: CLIAgentService stores the mapping
        Then: SessionBridge can retrieve the CLI session ID
        """
        from mcp_the_force.cli_agents.session_bridge import SessionBridge

        bridge = SessionBridge()

        # Store the mapping (as CLIAgentService would after parsing)
        await bridge.store_cli_session_id(
            project="test-project",
            session_id="user-session-123",
            cli_name="claude",
            cli_session_id="claude-session-abc123",
        )

        # Retrieve it
        stored_id = await bridge.get_cli_session_id(
            project="test-project",
            session_id="user-session-123",
            cli_name="claude",
        )

        # Invariant: What we stored is what we get back
        assert stored_id == "claude-session-abc123"

    @pytest.mark.asyncio
    async def test_multiple_clis_isolated_in_bridge(self, isolate_test_databases):
        """
        Given: Same user session used with different CLIs
        When: Each CLI stores its session ID
        Then: Each CLI's session ID is stored separately
        """
        from mcp_the_force.cli_agents.session_bridge import SessionBridge

        bridge = SessionBridge()

        # Same user session, different CLIs
        await bridge.store_cli_session_id("proj", "user-sess", "claude", "claude-id")
        await bridge.store_cli_session_id("proj", "user-sess", "codex", "codex-thread")
        await bridge.store_cli_session_id("proj", "user-sess", "gemini", "gemini-id")

        # Invariant: Each CLI has its own mapping
        assert (
            await bridge.get_cli_session_id("proj", "user-sess", "claude")
            == "claude-id"
        )
        assert (
            await bridge.get_cli_session_id("proj", "user-sess", "codex")
            == "codex-thread"
        )
        assert (
            await bridge.get_cli_session_id("proj", "user-sess", "gemini")
            == "gemini-id"
        )


# =============================================================================
# CP-CROSS-TOOL: Full Flow with Resume
# =============================================================================


@pytest.mark.integration
@pytest.mark.cli_agents
class TestFullFlowWithResume:
    """
    Tests the complete flow: new session → store → resume with same CLI.

    Flow: work_with → resolve → execute → parse → store → [later] → lookup → resume
    Invariant: Second call to same CLI uses --resume with correct session ID
    """

    @pytest.mark.asyncio
    async def test_second_call_uses_resume_flag(self, isolate_test_databases):
        """
        Given: First call created a Claude session
        When: Second call is made with same user session_id
        Then: CLIAgentService uses --resume with the stored CLI session ID
        """
        from mcp_the_force.cli_agents.session_bridge import SessionBridge
        from mcp_the_force.cli_plugins.registry import get_cli_plugin

        bridge = SessionBridge()

        # Simulate first call stored a session
        await bridge.store_cli_session_id(
            project="mcp-the-force",
            session_id="user-session",
            cli_name="claude",
            cli_session_id="claude-stored-id",
        )

        # Second call: lookup existing session
        existing_id = await bridge.get_cli_session_id(
            project="mcp-the-force",
            session_id="user-session",
            cli_name="claude",
        )

        assert existing_id is not None, "Should find existing session"

        # Build resume command
        plugin = get_cli_plugin("claude")
        command = plugin.build_resume_args(
            session_id=existing_id,
            task="Continue the task",
        )

        # Invariant: Resume command includes the stored session ID
        assert "--resume" in command
        assert "claude-stored-id" in command


# =============================================================================
# CP-MCP-WIRING: Tool Registration and Execution
# =============================================================================


@pytest.mark.integration
@pytest.mark.cli_agents
class TestMCPToolWiring:
    """
    Tests that work_with and consult_with are properly registered and routed.

    Flow: TOOL_REGISTRY → get_tool → execute → LocalService
    Invariant: Tools are registered with correct service class bindings
    """

    def test_work_with_registered_with_cli_service(self):
        """
        Given: Tool registry is populated
        When: We look up work_with
        Then: It's bound to CLIAgentService
        """
        from mcp_the_force.tools.registry import get_tool

        metadata = get_tool("work_with")
        assert metadata is not None, "work_with should be registered"

        # Check it's a LocalService pattern
        spec_class = metadata.spec_class
        service_cls = getattr(spec_class, "service_cls", None)

        assert service_cls is not None, "work_with should have service_cls"
        assert service_cls.__name__ == "CLIAgentService"

    def test_consult_with_registered_with_consultation_service(self):
        """
        Given: Tool registry is populated
        When: We look up consult_with
        Then: It's bound to ConsultationService
        """
        from mcp_the_force.tools.registry import get_tool

        metadata = get_tool("consult_with")
        assert metadata is not None, "consult_with should be registered"

        spec_class = metadata.spec_class
        service_cls = getattr(spec_class, "service_cls", None)

        assert service_cls is not None, "consult_with should have service_cls"
        assert service_cls.__name__ == "ConsultationService"

    @pytest.mark.asyncio
    async def test_work_with_executor_routes_to_service(self, isolate_test_databases):
        """
        Given: work_with tool metadata
        When: execute() is called
        Then: It invokes CLIAgentService.execute() with correct args
        """
        from mcp_the_force.tools.registry import get_tool
        from mcp_the_force.tools.executor import execute
        from mcp_the_force.local_services.cli_agent_service import CLIAgentService

        metadata = get_tool("work_with")

        # Mock the service's execute method
        with patch.object(
            CLIAgentService, "execute", new_callable=AsyncMock
        ) as mock_service:
            mock_service.return_value = "Mocked response"

            _result = await execute(
                metadata,
                agent="claude-sonnet-4-5",
                task="Test task",
                session_id="test-session",
                role="default",
            )

            # Invariant: Service was called with correct args
            mock_service.assert_called_once()
            call_kwargs = mock_service.call_args.kwargs
            assert call_kwargs["agent"] == "claude-sonnet-4-5"
            assert call_kwargs["task"] == "Test task"
            assert call_kwargs["session_id"] == "test-session"


def test_cli_wiring_integration_tests_load():
    """Meta-test: Verify integration test file loads correctly."""
    assert True
