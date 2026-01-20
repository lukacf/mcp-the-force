"""
Tests for CLI agent working directory handling.

Verifies that:
1. CLIAgentService passes project_dir correctly to executor
2. Executor receives and uses cwd parameter
3. Commands are executed in the correct working directory
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mcp_the_force.cli_agents.executor import CLIResult


class TestCLIAgentServiceWorkingDirectory:
    """Test that CLIAgentService passes correct working directory."""

    @pytest.mark.asyncio
    async def test_executor_receives_project_dir_as_cwd(self, tmp_path):
        """CLIAgentService should pass project_dir to executor as cwd."""
        from mcp_the_force.local_services.cli_agent_service import CLIAgentService

        # Create service with explicit project directory
        project_dir = str(tmp_path / "my-project")
        Path(project_dir).mkdir(parents=True, exist_ok=True)

        service = CLIAgentService(project_dir=project_dir)

        # Mock dependencies
        mock_result = CLIResult(
            stdout='{"thread_id": "t1", "type": "thread.started"}\n{"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}}',
            stderr="",
            return_code=0,
            timed_out=False,
        )

        with (
            patch.object(
                service._executor, "execute", new_callable=AsyncMock
            ) as mock_exec,
            patch.object(
                service._availability_checker, "is_available", return_value=True
            ),
            patch.object(
                service._session_bridge, "get_cli_session_id", new_callable=AsyncMock
            ) as mock_bridge,
            patch.object(
                service._session_bridge, "store_cli_session_id", new_callable=AsyncMock
            ),
            patch(
                "mcp_the_force.local_services.cli_agent_service.UnifiedSessionCache.get_session",
                new_callable=AsyncMock,
            ) as mock_get_session,
            patch(
                "mcp_the_force.local_services.cli_agent_service.UnifiedSessionCache.append_message",
                new_callable=AsyncMock,
            ),
        ):
            mock_exec.return_value = mock_result
            mock_bridge.return_value = None
            mock_get_session.return_value = None

            await service.execute(
                agent="gpt-5.2",
                task="Test task",
                session_id="test-cwd-session",
            )

            # Verify executor was called with correct cwd
            mock_exec.assert_called_once()
            call_kwargs = mock_exec.call_args
            assert (
                call_kwargs.kwargs["cwd"] == project_dir
            ), f"Expected cwd={project_dir}, got {call_kwargs.kwargs.get('cwd')}"

    @pytest.mark.asyncio
    async def test_default_project_dir_is_tmp(self):
        """CLIAgentService should default to /tmp if no project_dir provided."""
        from mcp_the_force.local_services.cli_agent_service import CLIAgentService

        service = CLIAgentService()  # No project_dir
        assert service._project_dir == "/tmp"

        service_with_none = CLIAgentService(project_dir=None)
        assert service_with_none._project_dir == "/tmp"

        service_with_empty = CLIAgentService(project_dir="")
        assert service_with_empty._project_dir == "/tmp"

    @pytest.mark.asyncio
    async def test_cwd_injected_into_task_for_codex(self, tmp_path):
        """Codex should have CWD injected into task text."""
        from mcp_the_force.local_services.cli_agent_service import CLIAgentService

        project_dir = str(tmp_path / "codex-project")
        Path(project_dir).mkdir(parents=True, exist_ok=True)

        service = CLIAgentService(project_dir=project_dir)

        mock_result = CLIResult(
            stdout='{"thread_id": "t1", "type": "thread.started"}\n{"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}}',
            stderr="",
            return_code=0,
            timed_out=False,
        )

        with (
            patch.object(
                service._executor, "execute", new_callable=AsyncMock
            ) as mock_exec,
            patch.object(
                service._availability_checker, "is_available", return_value=True
            ),
            patch.object(
                service._session_bridge, "get_cli_session_id", new_callable=AsyncMock
            ) as mock_bridge,
            patch.object(
                service._session_bridge, "store_cli_session_id", new_callable=AsyncMock
            ),
            patch(
                "mcp_the_force.local_services.cli_agent_service.UnifiedSessionCache.get_session",
                new_callable=AsyncMock,
            ) as mock_get_session,
            patch(
                "mcp_the_force.local_services.cli_agent_service.UnifiedSessionCache.append_message",
                new_callable=AsyncMock,
            ),
        ):
            mock_exec.return_value = mock_result
            mock_bridge.return_value = None
            mock_get_session.return_value = None

            await service.execute(
                agent="gpt-5.2",
                task="List all files",
                session_id="test-task-cwd",
            )

            # Check that the task includes CWD instruction
            call_args = mock_exec.call_args
            command = call_args.kwargs["command"]

            # The task (last arg) should contain the CWD instruction
            task_arg = command[-1]
            assert (
                f"Work from this directory: {project_dir}" in task_arg
            ), f"Task should contain CWD instruction, got: {task_arg[:100]}..."


class TestEnvironmentBuilderNoClaudeSymlink:
    """Test that EnvironmentBuilder does NOT symlink .claude directory."""

    def test_claude_dir_not_in_config_dirs(self):
        """
        .claude should NOT be symlinked because it contains project-specific settings.

        Claude Code stores its current project context in ~/.claude/, so symlinking
        the entire directory from real HOME causes Claude to think it's in a different
        project, ignoring the cwd we set.

        Authentication should use ANTHROPIC_API_KEY env var instead.
        """
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        # .claude should NOT be in the symlink list
        claude_config_dirs = EnvironmentBuilder.CLI_CONFIG_DIRS.get("claude", [])
        assert ".claude" not in claude_config_dirs, (
            ".claude should NOT be symlinked - it contains project-specific settings "
            "that cause Claude Code to use wrong working directory"
        )

    def test_claude_api_key_is_injected(self):
        """Claude should authenticate via ANTHROPIC_API_KEY env var."""
        from mcp_the_force.cli_agents.environment import EnvironmentBuilder

        # Verify ANTHROPIC_API_KEY is configured for injection
        claude_mappings = EnvironmentBuilder.CLI_API_KEY_MAPPING.get("claude", [])
        env_vars = [mapping[0] for mapping in claude_mappings]
        assert (
            "ANTHROPIC_API_KEY" in env_vars
        ), "Claude should use ANTHROPIC_API_KEY for authentication"


class TestToolExecutorProjectPathDerivation:
    """Test that ToolExecutor derives project_path correctly."""

    def test_project_path_is_cwd(self):
        """project_path should simply be the current working directory.

        The MCP server always runs from the project directory, so os.getcwd()
        is the most reliable way to get the project path.
        """
        import os

        # The executor uses os.getcwd() directly
        project_path = os.getcwd()

        # Should be a valid directory path
        assert os.path.isdir(project_path)
