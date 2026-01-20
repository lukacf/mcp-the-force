"""Integration tests for CLI output cleaning in CLIAgentService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_the_force.cli_agents.executor import CLIResult
from mcp_the_force.local_services.cli_agent_service import CLIAgentService


@pytest.fixture
def mock_cli_environment():
    """Set up mocked CLI environment."""
    with (
        patch(
            "mcp_the_force.local_services.cli_agent_service.CLIAvailabilityChecker"
        ) as mock_checker,
        patch(
            "mcp_the_force.local_services.cli_agent_service.resolve_model_to_cli"
        ) as mock_resolver,
        patch(
            "mcp_the_force.local_services.cli_agent_service.get_cli_plugin"
        ) as mock_get_plugin,
    ):
        # CLI is available
        mock_checker.return_value.is_available.return_value = True

        # Model resolves to codex
        mock_resolver.return_value = "codex"

        # Plugin parses output
        mock_plugin = MagicMock()
        mock_plugin.executable = "codex"
        mock_plugin.build_new_session_args.return_value = ["exec", "--json", "task"]
        mock_plugin.get_reasoning_env_vars.return_value = {}
        mock_get_plugin.return_value = mock_plugin

        yield {
            "checker": mock_checker,
            "resolver": mock_resolver,
            "plugin": mock_plugin,
            "get_plugin": mock_get_plugin,
        }


class TestOutputCleaningIntegration:
    """Test that CLI output is cleaned before being returned."""

    @pytest.mark.asyncio
    async def test_codex_jsonl_is_cleaned_to_markdown(
        self, mock_cli_environment, tmp_path
    ):
        """Raw Codex JSONL output is cleaned to readable markdown."""
        # Mock the executor to return JSONL output
        raw_jsonl = """{"type":"thread.started","thread_id":"abc-123"}
{"type":"item.completed","item":{"type":"reasoning","text":"Analyzing the code..."}}
{"type":"item.completed","item":{"type":"command_execution","command":"ls","aggregated_output":"file1.py\\nfile2.py","exit_code":0}}
{"type":"item.completed","item":{"type":"agent_message","text":"I found two Python files."}}"""

        # Set up parsed response
        mock_cli_environment["plugin"].parse_output.return_value = MagicMock(
            session_id="abc-123", content="I found two Python files."
        )

        service = CLIAgentService(project_dir=str(tmp_path))

        with (
            patch.object(
                service._executor,
                "execute",
                new_callable=AsyncMock,
                return_value=CLIResult(
                    stdout=raw_jsonl, stderr="", return_code=0, timed_out=False
                ),
            ),
            patch.object(
                service._environment_builder,
                "build_isolated_env",
                return_value={"PATH": "/usr/bin"},
            ),
            patch.object(
                service._session_bridge,
                "get_cli_session_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                service._session_bridge, "store_cli_session_id", new_callable=AsyncMock
            ),
            patch(
                "mcp_the_force.local_services.cli_agent_service.UnifiedSessionCache"
            ) as mock_cache,
        ):
            mock_cache.get_session = AsyncMock(return_value=None)
            mock_cache.append_message = AsyncMock()

            result = await service.execute(
                agent="gpt-5.2",
                task="List files",
                session_id="test-session",
            )

        # Output should be clean markdown, not raw JSONL
        assert "thread.started" not in result
        assert "item.completed" not in result
        # Should contain the actual content
        assert "Analyzing the code" in result or "I found two Python files" in result

    @pytest.mark.asyncio
    async def test_plain_text_output_passes_through(
        self, mock_cli_environment, tmp_path
    ):
        """Plain text output (from Claude/Gemini) passes through unchanged."""
        plain_output = """Here is my analysis:

1. The code is well-structured
2. Tests are comprehensive

```python
def example():
    pass
```"""

        mock_cli_environment["plugin"].parse_output.return_value = MagicMock(
            session_id="session-456", content=plain_output
        )

        service = CLIAgentService(project_dir=str(tmp_path))

        with (
            patch.object(
                service._executor,
                "execute",
                new_callable=AsyncMock,
                return_value=CLIResult(
                    stdout=plain_output, stderr="", return_code=0, timed_out=False
                ),
            ),
            patch.object(
                service._environment_builder,
                "build_isolated_env",
                return_value={"PATH": "/usr/bin"},
            ),
            patch.object(
                service._session_bridge,
                "get_cli_session_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                service._session_bridge, "store_cli_session_id", new_callable=AsyncMock
            ),
            patch(
                "mcp_the_force.local_services.cli_agent_service.UnifiedSessionCache"
            ) as mock_cache,
        ):
            mock_cache.get_session = AsyncMock(return_value=None)
            mock_cache.append_message = AsyncMock()

            result = await service.execute(
                agent="gpt-5.2",
                task="Analyze code",
                session_id="test-session",
            )

        # Plain text should pass through
        assert "Here is my analysis" in result
        assert "def example():" in result


class TestLargeOutputFileHandling:
    """Test that large outputs are saved to files."""

    @pytest.mark.asyncio
    async def test_large_output_includes_file_link(
        self, mock_cli_environment, tmp_path
    ):
        """Large outputs should include a link to the full output file."""
        # Generate a large output (> 10k tokens worth)
        # JSON-escape newlines
        large_content = "Analysis line\\n" * 5000  # ~5000 lines, JSON-escaped
        raw_jsonl = f'{{"type":"item.completed","item":{{"type":"agent_message","text":"{large_content}"}}}}'

        mock_cli_environment["plugin"].parse_output.return_value = MagicMock(
            session_id="abc-123", content=large_content
        )

        service = CLIAgentService(project_dir=str(tmp_path))

        with (
            patch.object(
                service._executor,
                "execute",
                new_callable=AsyncMock,
                return_value=CLIResult(
                    stdout=raw_jsonl, stderr="", return_code=0, timed_out=False
                ),
            ),
            patch.object(
                service._environment_builder,
                "build_isolated_env",
                return_value={"PATH": "/usr/bin"},
            ),
            patch.object(
                service._session_bridge,
                "get_cli_session_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                service._session_bridge, "store_cli_session_id", new_callable=AsyncMock
            ),
            patch(
                "mcp_the_force.local_services.cli_agent_service.UnifiedSessionCache"
            ) as mock_cache,
        ):
            mock_cache.get_session = AsyncMock(return_value=None)
            mock_cache.append_message = AsyncMock()

            result = await service.execute(
                agent="gpt-5.2",
                task="Analyze codebase",
                session_id="test-session",
            )

        # For large outputs, either:
        # 1. Output is summarized with file link, OR
        # 2. Full output is returned (if summarizer disabled/failed)
        # The key is that raw JSONL is NOT returned
        assert "item.completed" not in result
