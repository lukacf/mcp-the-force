"""
OutputSummarizer: Always-summarize CLI output via fast API model.

REQ-4.3.2: CLI output is always summarized via gemini-3-flash-preview.
"""

from typing import Optional


class OutputSummarizer:
    """
    Summarizes CLI output for return to MCP client.

    Uses gemini-3-flash-preview for speed.
    """

    model_name: str = "gemini-3-flash-preview"

    prompt_template: str = """Summarize the following CLI output concisely.
Preserve key information: session IDs, results, errors, and important findings.

CLI Output:
{output}

Task Context (if provided):
{context}

Provide a clear, concise summary:"""

    async def summarize(
        self,
        output: str,
        task_context: Optional[str] = None,
    ) -> str:
        """
        Summarize CLI output.

        Args:
            output: Raw CLI output to summarize
            task_context: Optional context about the task

        Returns:
            Summarized output string
        """
        if not output or not output.strip():
            return ""

        raise NotImplementedError("OutputSummarizer.summarize not implemented")

    async def _call_gemini_flash(self, prompt: str) -> str:
        """Call gemini-3-flash-preview for summarization."""
        raise NotImplementedError("OutputSummarizer._call_gemini_flash not implemented")
