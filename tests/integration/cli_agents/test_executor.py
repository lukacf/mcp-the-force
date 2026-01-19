"""
Integration Tests: CLIExecutor ↔ subprocess ↔ Parser pipeline.

Choke Point: CP-CLI-SESSION (execution path)
Phase 1: Real tests that fail because code not implemented yet.
"""

import pytest


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_executor_spawns_subprocess_with_correct_env():
    """
    Wiring: Executor passes environment to subprocess.

    Given: An execution request with custom HOME
    When: CLIExecutor.execute() is called
    Then: The subprocess receives the modified environment
    """
    from mcp_the_force.cli_agents.executor import CLIExecutor

    executor = CLIExecutor()

    # Use 'printenv HOME' to verify environment is passed
    result = await executor.execute(
        command=["printenv", "HOME"],
        env={"HOME": "/tmp/isolated-test", "PATH": "/usr/bin:/bin"},
        timeout=10,
    )

    assert result.return_code == 0
    assert "/tmp/isolated-test" in result.stdout


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_executor_captures_stdout():
    """
    Wiring: Executor captures subprocess stdout.

    Given: A CLI command that outputs text
    When: CLIExecutor.execute() completes
    Then: stdout is captured in CLIResult
    """
    from mcp_the_force.cli_agents.executor import CLIExecutor

    executor = CLIExecutor()

    result = await executor.execute(
        command=["echo", "hello world"],
        env={},
        timeout=10,
    )

    assert result.return_code == 0
    assert "hello world" in result.stdout


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_executor_handles_timeout():
    """
    Wiring: Executor kills subprocess on timeout.

    Given: A command that would run for longer than timeout
    When: Timeout is reached
    Then: Process is killed, partial output returned, timed_out=True
    """
    from mcp_the_force.cli_agents.executor import CLIExecutor

    executor = CLIExecutor()

    # sleep 10 should be killed after 1 second
    result = await executor.execute(
        command=["sleep", "10"],
        env={},
        timeout=1,
    )

    assert result.timed_out is True


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_executor_handles_nonzero_exit():
    """
    Wiring: Executor captures non-zero exit codes.

    Given: A command that fails
    When: CLIExecutor.execute() completes
    Then: return_code reflects the failure
    """
    from mcp_the_force.cli_agents.executor import CLIExecutor

    executor = CLIExecutor()

    result = await executor.execute(
        command=["false"],  # 'false' always exits with code 1
        env={},
        timeout=10,
    )

    assert result.return_code != 0


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_executor_captures_stderr():
    """
    Wiring: Executor captures stderr separately.

    Given: A command that writes to stderr
    When: CLIExecutor.execute() completes
    Then: stderr is captured in CLIResult
    """
    from mcp_the_force.cli_agents.executor import CLIExecutor

    executor = CLIExecutor()

    # Use shell to redirect to stderr
    result = await executor.execute(
        command=["sh", "-c", "echo error >&2"],
        env={},
        timeout=10,
    )

    assert "error" in result.stderr


@pytest.mark.integration
@pytest.mark.cli_agents
class TestParserPipeline:
    """Integration: CLI output → Parser → ParsedCLIResponse."""

    @pytest.mark.asyncio
    async def test_claude_output_parsed_correctly(self):
        """
        Pipeline: Claude JSON → ClaudePlugin.parse_output → ParsedCLIResponse.

        Given: Real Claude CLI JSON output format
        When: Passed through plugin's parse_output
        Then: session_id and content extracted correctly
        """
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        # Sample Claude output (from RCT findings)
        claude_output = """[{"type":"system","subtype":"init","session_id":"abc-123-def","tools":["Read","Write"]},{"type":"result","subtype":"success","result":"Hello!","session_id":"abc-123-def"}]"""

        plugin = ClaudePlugin()
        result = plugin.parse_output(claude_output)

        assert result.session_id == "abc-123-def"
        assert "Hello" in result.content

    @pytest.mark.asyncio
    async def test_gemini_output_parsed_correctly(self):
        """
        Pipeline: Gemini JSON → GeminiPlugin.parse_output → ParsedCLIResponse.

        Given: Real Gemini CLI JSON output format
        When: Passed through plugin's parse_output
        Then: session_id and response extracted correctly
        """
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        # Sample Gemini output (from RCT findings)
        gemini_output = """{"session_id":"gemini-456-xyz","response":"The answer is 4","stats":{}}"""

        plugin = GeminiPlugin()
        result = plugin.parse_output(gemini_output)

        assert result.session_id == "gemini-456-xyz"
        assert "4" in result.content

    @pytest.mark.asyncio
    async def test_codex_jsonl_parsed_correctly(self):
        """
        Pipeline: Codex JSONL → CodexPlugin.parse_output → ParsedCLIResponse.

        Given: Real Codex CLI JSONL output (multiple lines)
        When: Passed through plugin's parse_output
        Then: thread_id extracted from thread.started event
        """
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        # Sample Codex JSONL output (from RCT findings)
        # Note: Codex uses thread_id, not session_id!
        # Content is in item.text (agent_message type only, not reasoning)
        codex_output = """{"thread_id":"codex-789-thread","type":"thread.started"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Done!"}}
{"type":"turn.completed"}"""

        plugin = CodexPlugin()
        result = plugin.parse_output(codex_output)

        assert result.session_id == "codex-789-thread"  # thread_id mapped to session_id
        assert "Done" in result.content


@pytest.mark.integration
@pytest.mark.cli_agents
@pytest.mark.asyncio
async def test_resume_flag_added_when_mapping_exists(isolate_test_databases):
    """
    CP-CLI-SESSION: Resume flag injection.

    Given: SessionBridge has a CLI session mapping
    When: CLIAgentService builds the command for Claude
    Then: --resume <id> is included in the command
    """
    from mcp_the_force.cli_agents.session_bridge import SessionBridge
    from mcp_the_force.cli_plugins.claude import ClaudePlugin

    # Pre-populate session mapping
    bridge = SessionBridge()
    await bridge.store_cli_session_id(
        "proj", "resume-test", "claude", "existing-cli-session"
    )

    # Build command - should include resume flag
    plugin = ClaudePlugin()
    cli_session_id = await bridge.get_cli_session_id("proj", "resume-test", "claude")

    command = plugin.build_resume_args(
        session_id=cli_session_id,
        task="Continue working",
    )

    assert "--resume" in command
    assert "existing-cli-session" in command


def test_executor_integration_tests_load():
    """Meta-test: Verify integration test file loads correctly."""
    assert True
