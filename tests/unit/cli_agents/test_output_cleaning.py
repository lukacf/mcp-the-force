"""Tests for CLI output cleaning and file handling.

Verifies that:
1. Codex JSONL output extracts only agent_message (not reasoning/commands)
2. Output files contain cleaned agent_message content, NOT raw JSONL
3. Empty parsed content does NOT fall back to raw JSONL
"""

import pytest
from unittest.mock import AsyncMock, patch

from mcp_the_force.cli_agents.output_cleaner import OutputCleaner


class TestOutputCleanerCodex:
    """Test OutputCleaner with Codex JSONL format."""

    def test_clean_jsonl_to_markdown(self):
        """JSONL with agent_message should extract only agent_message content."""
        cleaner = OutputCleaner()

        # Sample Codex JSONL output
        jsonl_output = """{"thread_id": "thread_abc123", "type": "thread.started"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "I'll help you with that task."}}
{"type": "item.completed", "item": {"type": "command_execution", "command": "/bin/zsh -lc 'ls -la'", "aggregated_output": "file1.txt\\nfile2.txt", "exit_code": 0}}
{"type": "turn.completed"}"""

        result = cleaner.clean(jsonl_output)

        # Should be clean markdown, NOT raw JSONL
        assert "thread_id" not in result.markdown.lower()
        assert "I'll help you with that task." in result.markdown
        # Commands should NOT be in output (only agent_message)
        assert "ls -la" not in result.markdown
        assert result.thread_id == "thread_abc123"

    def test_clean_jsonl_no_content_does_not_return_raw_jsonl(self):
        """JSONL without item.completed events should return empty, NOT raw JSONL.

        This is a regression test for a bug where empty parsed content
        would fall back to raw stdout (JSONL), causing output files to
        contain unreadable JSON instead of clean markdown.
        """
        cleaner = OutputCleaner()

        # JSONL with no item.completed events (just thread lifecycle events)
        jsonl_output = """{"thread_id": "thread_xyz789", "type": "thread.started"}
{"type": "turn.started"}
{"type": "turn.completed"}"""

        result = cleaner.clean(jsonl_output)

        # Should NOT contain raw JSONL - either empty or cleaned metadata only
        assert "thread_id" not in result.markdown
        assert "type" not in result.markdown
        # Thread ID should still be extracted even if no content
        assert result.thread_id == "thread_xyz789"

    def test_clean_jsonl_reasoning_item_excluded(self):
        """Reasoning items should NOT be included in output."""
        cleaner = OutputCleaner()

        jsonl_output = """{"thread_id": "thread_test", "type": "thread.started"}
{"type": "item.completed", "item": {"type": "reasoning", "text": "Let me think about this..."}}"""

        result = cleaner.clean(jsonl_output)

        # Reasoning should NOT be in output
        assert "Let me think about this" not in result.markdown
        assert result.markdown == ""

    def test_clean_plain_text_passthrough(self):
        """Non-JSONL output should pass through as-is."""
        cleaner = OutputCleaner()

        plain_output = """This is plain text output
from a CLI that doesn't use JSONL format."""

        result = cleaner.clean(plain_output)

        assert "This is plain text output" in result.markdown
        assert result.thread_id is None


class TestCLIAgentServiceOutputHandling:
    """Test that CLIAgentService correctly uses cleaned output."""

    @pytest.mark.asyncio
    async def test_output_file_contains_cleaned_markdown_not_raw_jsonl(self, tmp_path):
        """Output file should contain only agent_message content, NOT raw JSONL.

        This is the critical P0 bug: when saving large outputs to files,
        the file must contain the cleaned agent_message content, not the
        raw JSONL that was in stdout or the full transcript.
        """
        from mcp_the_force.local_services.cli_agent_service import CLIAgentService
        from mcp_the_force.cli_agents.executor import CLIResult

        # Sample JSONL output from Codex
        raw_jsonl = """{"thread_id": "thread_abc123", "type": "thread.started"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "Here is my response to your task."}}
{"type": "item.completed", "item": {"type": "command_execution", "command": "/bin/zsh -lc 'echo hello'", "aggregated_output": "hello", "exit_code": 0}}
{"type": "turn.completed"}"""

        # Create service with mocked dependencies
        service = CLIAgentService(project_dir=str(tmp_path))

        # Override output directory to use temp path
        service._output_file_handler._output_dir = str(tmp_path)

        # Mock executor to return raw JSONL
        mock_result = CLIResult(
            stdout=raw_jsonl,
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
            patch.object(
                service._summarizer, "summarize", new_callable=AsyncMock
            ) as mock_summarize,
            # Force output to exceed threshold so it saves to file
            patch.object(service._output_cleaner, "_token_threshold", 10),
        ):
            mock_exec.return_value = mock_result
            mock_bridge.return_value = None  # No existing session
            mock_get_session.return_value = None
            # Return truncated summary to trigger file save with link
            mock_summarize.return_value = "Summary: Task completed successfully."

            await service.execute(
                agent="gpt-5.2",
                task="Test task",
                session_id="test-session-123",
            )

        # Find the output file
        output_files = list(tmp_path.glob("work_with-*.md"))
        assert (
            len(output_files) == 1
        ), f"Expected 1 output file, found {len(output_files)}"

        # Read file contents
        file_content = output_files[0].read_text()

        # File should contain clean markdown, NOT raw JSONL
        assert (
            "thread_id" not in file_content
        ), "Output file contains raw JSONL 'thread_id'"
        assert '{"type":' not in file_content, "Output file contains raw JSON"
        assert (
            '"item.completed"' not in file_content
        ), "Output file contains JSONL event type"

        # File should contain only agent_message content
        assert "Here is my response to your task." in file_content
        # Commands should NOT be in output file (only agent_message)
        assert "echo hello" not in file_content
