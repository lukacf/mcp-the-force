"""
Unit Tests: Output Summarizer (REQ-4.3.2).

Tests for the always-summarize behavior using gemini-3-flash-preview.
"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.xfail(
    reason="Phase 2: OutputSummarizer not yet implemented", raises=NotImplementedError
)
class TestOutputSummarizer:
    """Unit tests for output summarization."""

    @pytest.mark.asyncio
    async def test_always_summarizes_cli_output(self):
        """
        REQ-4.3.2: CLI output is always summarized via API model.

        Given: Raw CLI output (potentially large)
        When: Output is processed for return to MCP client
        Then: Summarization is always applied via gemini-3-flash-preview
        """
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        raw_output = "A very long CLI output..." * 100

        summarizer = OutputSummarizer()

        with patch.object(
            summarizer, "_call_gemini_flash", new_callable=AsyncMock
        ) as mock_summarize:
            mock_summarize.return_value = "Summary: Key findings from the output..."

            result = await summarizer.summarize(raw_output)

            # Should ALWAYS call the summarizer, regardless of output size
            mock_summarize.assert_called_once()
            assert "Summary" in result

    @pytest.mark.asyncio
    async def test_uses_gemini_flash_for_speed(self):
        """
        Summarization uses gemini-3-flash-preview for speed.

        Given: CLI output to summarize
        When: Summarization is requested
        Then: gemini-3-flash-preview is used (not slower models)
        """
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        summarizer = OutputSummarizer()

        assert summarizer.model_name == "gemini-3-flash-preview"

    @pytest.mark.asyncio
    async def test_preserves_critical_information(self):
        """
        Summarization preserves critical information.

        Given: CLI output with session ID and key content
        When: Summarized
        Then: Session ID and key findings are preserved in summary
        """
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        raw_output = """
        Session ID: abc-123-def
        Result: Successfully created 5 new files
        Errors: None
        """

        summarizer = OutputSummarizer()

        with patch.object(
            summarizer, "_call_gemini_flash", new_callable=AsyncMock
        ) as mock_summarize:
            mock_summarize.return_value = "Created 5 files, session abc-123-def"

            _result = await summarizer.summarize(raw_output)

            # Verify call was made with the raw output
            call_args = mock_summarize.call_args[0][0]
            assert "abc-123-def" in call_args
            assert "5 new files" in call_args

    @pytest.mark.asyncio
    async def test_handles_empty_output(self):
        """
        Summarizer handles empty output gracefully.

        Given: Empty CLI output
        When: Summarization is attempted
        Then: Returns appropriate message without API call
        """
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        summarizer = OutputSummarizer()

        result = await summarizer.summarize("")

        # Empty output should return quickly without API call
        assert result == "" or "No output" in result

    @pytest.mark.asyncio
    async def test_includes_metadata_in_context(self):
        """
        Summarizer includes task metadata in summarization context.

        Given: CLI output and task context
        When: Summarization is requested
        Then: Task context is provided to model for better summarization
        """
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        summarizer = OutputSummarizer()

        with patch.object(
            summarizer, "_call_gemini_flash", new_callable=AsyncMock
        ) as mock_summarize:
            mock_summarize.return_value = "Summary with context"

            await summarizer.summarize(
                output="Raw output here",
                task_context="User asked to fix the authentication bug",
            )

            # Verify context was passed to the model
            call_args = mock_summarize.call_args[0]
            prompt = call_args[0]
            assert "authentication" in prompt.lower() or "task" in prompt.lower()


class TestSummarizationPrompt:
    """Unit tests for the summarization prompt template."""

    def test_prompt_template_exists(self):
        """Summarization prompt template is defined."""
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        summarizer = OutputSummarizer()

        assert hasattr(summarizer, "prompt_template")
        assert len(summarizer.prompt_template) > 0

    def test_prompt_includes_output_placeholder(self):
        """Prompt template has placeholder for CLI output."""
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        summarizer = OutputSummarizer()

        assert (
            "{output}" in summarizer.prompt_template
            or "output" in summarizer.prompt_template.lower()
        )
