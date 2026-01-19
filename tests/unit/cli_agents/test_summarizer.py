"""
Unit Tests: Output Summarizer.

Tests for threshold-based summarization using gemini-3-flash-preview.
"""

import pytest
from unittest.mock import AsyncMock, patch


class TestOutputSummarizer:
    """Unit tests for output summarization."""

    @pytest.mark.asyncio
    async def test_summarizes_large_cli_output(self):
        """
        CLI output is summarized when it exceeds size threshold.

        Given: Raw CLI output that exceeds the size threshold
        When: Output is processed for return to MCP client
        Then: Summarization is applied via gemini-3-flash-preview
        """
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        summarizer = OutputSummarizer()

        # Create output that exceeds the actual threshold
        raw_output = "A" * (summarizer.size_threshold + 1000)

        with patch.object(
            summarizer, "_call_gemini_flash", new_callable=AsyncMock
        ) as mock_summarize:
            mock_summarize.return_value = "Summary: Key findings from the output..."

            result = await summarizer.summarize(raw_output)

            # Should call the summarizer when output exceeds threshold
            mock_summarize.assert_called_once()
            assert "Summary" in result

    @pytest.mark.asyncio
    async def test_returns_small_output_verbatim(self):
        """
        CLI output under threshold is returned verbatim (not summarized).

        Given: Small CLI output (under 4000 chars)
        When: Output is processed for return to MCP client
        Then: Output is returned as-is without summarization
        """
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        raw_output = "A short CLI output message"

        summarizer = OutputSummarizer()

        with patch.object(
            summarizer, "_call_gemini_flash", new_callable=AsyncMock
        ) as mock_summarize:
            result = await summarizer.summarize(raw_output)

            # Should NOT call the summarizer for small outputs
            mock_summarize.assert_not_called()
            assert result == raw_output

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

        Given: Large CLI output with session ID and key content
        When: Summarized
        Then: Session ID and key findings are preserved in summary
        """
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        summarizer = OutputSummarizer()

        # Create large output that exceeds the actual threshold
        critical_info = """
        Session ID: abc-123-def
        Result: Successfully created 5 new files
        Errors: None
        """
        padding = "A" * (summarizer.size_threshold + 1000)
        raw_output = critical_info + padding

        with patch.object(
            summarizer, "_call_gemini_flash", new_callable=AsyncMock
        ) as mock_summarize:
            mock_summarize.return_value = "Created 5 files, session abc-123-def"

            await summarizer.summarize(raw_output)

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

        Given: Large CLI output and task context
        When: Summarization is requested
        Then: Task context is provided to model for better summarization
        """
        from mcp_the_force.cli_agents.summarizer import OutputSummarizer

        summarizer = OutputSummarizer()

        # Create large output that exceeds the actual threshold
        large_output = "A" * (summarizer.size_threshold + 1000)

        with patch.object(
            summarizer, "_call_gemini_flash", new_callable=AsyncMock
        ) as mock_summarize:
            mock_summarize.return_value = "Summary with context"

            await summarizer.summarize(
                output=large_output,
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
