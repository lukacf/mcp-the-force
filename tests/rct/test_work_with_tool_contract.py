"""
RCT: work_with Tool Contract Tests

Regression tests for bugs reported 2026-01-18:
1. agent parameter should list available CLI models (not "claude", "gemini", "codex")
2. context parameter should NOT exist
3. CWD should be auto-injected into task prompt
"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.rct
class TestWorkWithToolContract:
    """
    Gate 0 tests for work_with tool parameter contract.

    These tests must pass BEFORE implementing features.
    """

    def test_agent_parameter_lists_cli_models_not_cli_names(self):
        """
        REGRESSION: agent parameter description said "Options: 'claude', 'gemini', 'codex'"
        but these are CLI names, not model names. Users got "Model not found in registry: claude"

        FIX: Description should list actual model names like 'claude-sonnet-4-5', 'gpt-5.2', etc.
        """
        from mcp_the_force.tools.registry import get_tool

        metadata = get_tool("work_with")
        assert metadata is not None

        # Get the agent parameter schema
        params = metadata.parameters
        agent_param = params.get("agent")
        assert agent_param is not None, "agent parameter should exist"

        description = agent_param.description
        assert description is not None, "agent parameter should have description"

        # Should NOT list bare CLI names as valid options
        assert (
            "Options: 'claude', 'gemini', 'codex'" not in description
        ), "Description should not list bare CLI names as valid options"

        # Should list actual model names
        assert (
            "claude-sonnet-4-5" in description or "Available models" in description
        ), "Description should list actual model names or indicate they are available"

    def test_agent_parameter_dynamically_generated_from_blueprints(self):
        """
        The agent parameter description should be generated from the blueprint registry,
        not hardcoded. This ensures new models are automatically listed.
        """
        from mcp_the_force.tools.registry import get_tool
        from mcp_the_force.cli_agents.model_cli_resolver import get_all_cli_models

        metadata = get_tool("work_with")
        params = metadata.parameters
        agent_param = params.get("agent")
        assert agent_param is not None
        description = agent_param.description
        assert description is not None

        # Get actual CLI models from registry
        cli_models = get_all_cli_models()
        assert len(cli_models) > 0, "Should have at least one CLI model"

        # Pick a model we know exists
        sample_model = list(cli_models.keys())[0]

        # Description should mention this model
        assert (
            sample_model in description or "Available models" in description
        ), f"Description should include {sample_model} or dynamically reference available models"

    def test_context_parameter_does_not_exist(self):
        """
        REGRESSION: work_with had a 'context' parameter for file paths,
        but this doesn't work (sub-agents can't access those paths) and should not exist.

        FIX: Remove context parameter entirely. CWD is auto-injected instead.
        """
        from mcp_the_force.tools.registry import get_tool

        metadata = get_tool("work_with")
        params = metadata.parameters

        assert "context" not in params, (
            "work_with should NOT have a 'context' parameter - "
            "project directory is auto-injected by CLIAgentService"
        )

    def test_agent_parameter_accepts_model_names_not_cli_names(self):
        """
        Verify that agent parameter accepts model names like 'claude-sonnet-4-5',
        not just CLI names like 'claude'.
        """
        from mcp_the_force.cli_agents.model_cli_resolver import resolve_model_to_cli
        from mcp_the_force.cli_agents.model_cli_resolver import ModelNotFoundError

        # Should accept full model names
        cli_name = resolve_model_to_cli("claude-sonnet-4-5")
        assert cli_name == "claude"

        # Should reject bare CLI names (they're not in the model registry)
        with pytest.raises(
            ModelNotFoundError, match="Model not found in registry: claude"
        ):
            resolve_model_to_cli("claude")


@pytest.mark.rct
class TestCWDAutoInjection:
    """
    Gate 0 tests for automatic CWD injection into task prompts.
    """

    @pytest.mark.asyncio
    async def test_cwd_auto_injected_into_task(self, isolate_test_databases):
        """
        REGRESSION: Users had to manually add "CWD: /path/to/project" to task string.
        Sub-agents couldn't find files without explicit path guidance.

        FIX: CLIAgentService should automatically inject "Work from this directory: {cwd}"
        into the task prompt.
        """
        from mcp_the_force.local_services.cli_agent_service import CLIAgentService
        from mcp_the_force.cli_agents.executor import CLIExecutor, CLIResult
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        service = CLIAgentService(project_dir="/Users/test/my-project")

        # Mock CLI plugin and execution
        captured_command = None

        async def mock_execute(command, env, timeout, cwd=None):
            nonlocal captured_command
            captured_command = command
            # Return valid Claude JSON output
            import json

            return CLIResult(
                stdout=json.dumps(
                    [
                        {"type": "system", "session_id": "test-123"},
                        {"type": "result", "result": "done", "session_id": "test-123"},
                    ]
                ),
                stderr="",
                return_code=0,
                timed_out=False,
            )

        original_build_new = ClaudePlugin.build_new_session_args

        def patched_build_new(self, task, context_dirs=None, role=None):
            # Capture the task that was passed
            result = original_build_new(self, task, context_dirs, role)
            # Inject task into result for inspection
            result.append(f"__TASK__:{task}")
            return result

        with patch.object(CLIExecutor, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = mock_execute
            with patch.object(
                ClaudePlugin, "build_new_session_args", patched_build_new
            ):
                await service.execute(
                    agent="claude-sonnet-4-5",
                    task="Review README.md",
                    session_id="test-session",
                )

                # Extract task from captured command
                assert captured_command is not None, "Should have captured command"
                task_marker = [
                    arg for arg in captured_command if arg.startswith("__TASK__:")
                ]
                assert len(task_marker) > 0, "Should have found task marker in command"

                actual_task = task_marker[0].replace("__TASK__:", "")
                assert (
                    "/Users/test/my-project" in actual_task
                ), f"Task should include project directory path, got: {actual_task}"
                assert (
                    "Work from this directory:" in actual_task
                ), f"Task should have CWD guidance prepended, got: {actual_task}"

    @pytest.mark.asyncio
    async def test_cwd_not_injected_for_tmp(self, isolate_test_databases):
        """
        When project_dir is /tmp (default), don't inject CWD into task.
        """
        from mcp_the_force.local_services.cli_agent_service import CLIAgentService
        from mcp_the_force.cli_agents.executor import CLIExecutor, CLIResult

        service = CLIAgentService(project_dir="/tmp")

        captured_task = None

        async def mock_execute(command, env, timeout, cwd=None):
            nonlocal captured_task
            if "-p" in command:
                idx = command.index("-p")
                captured_task = command[idx + 1]
            return CLIResult(
                stdout='{"session_id":"test-123","response":"done"}',
                stderr="",
                return_code=0,
                timed_out=False,
            )

        with patch.object(CLIExecutor, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = mock_execute

            await service.execute(
                agent="claude-sonnet-4-5",
                task="Simple task",
                session_id="test-session",
            )

            # Should not inject CWD for /tmp
            if captured_task:
                assert "Work from this directory:" not in captured_task
                assert "/tmp" not in captured_task or captured_task == "Simple task"


@pytest.mark.rct
class TestProjectDirAsContext:
    """
    Gate 0 tests for automatic project directory as context.

    Note: Command format for --add-dir is validated in test_cli_command_formats.py.
    This test validates the SERVICE LAYER wiring - that CLIAgentService actually
    passes project_dir to the CLI plugin's build_new_session_args().
    """

    @pytest.mark.asyncio
    async def test_service_passes_project_dir_to_cli_plugin(
        self, isolate_test_databases
    ):
        """
        Validate that CLIAgentService passes project_dir to CLI plugin.

        This is a wiring test - does the service layer correctly wire up
        the project directory to the command builder?
        """
        from mcp_the_force.local_services.cli_agent_service import CLIAgentService
        from mcp_the_force.cli_agents.executor import CLIExecutor, CLIResult
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        service = CLIAgentService(project_dir="/Users/test/my-project")

        captured_context_dirs = None
        original_build_new = ClaudePlugin.build_new_session_args

        def patched_build_new(self, task, context_dirs=None, role=None):
            nonlocal captured_context_dirs
            captured_context_dirs = context_dirs
            return original_build_new(self, task, context_dirs, role)

        async def mock_execute(command, env, timeout, cwd=None):
            return CLIResult(
                stdout='[{"type":"system","session_id":"test-123"},{"type":"result","result":"done","session_id":"test-123"}]',
                stderr="",
                return_code=0,
                timed_out=False,
            )

        with patch.object(CLIExecutor, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = mock_execute
            with patch.object(
                ClaudePlugin, "build_new_session_args", patched_build_new
            ):
                await service.execute(
                    agent="claude-sonnet-4-5",
                    task="Review README.md",
                    session_id="test-session",
                )

                # Verify project_dir was passed to CLI plugin
                assert (
                    captured_context_dirs is not None
                ), "Service should pass context_dirs to CLI plugin"
                assert (
                    "/Users/test/my-project" in captured_context_dirs
                ), f"Project directory should be in context_dirs, got: {captured_context_dirs}"
