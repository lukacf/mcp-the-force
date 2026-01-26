"""
OutputSummarizer: Always-summarize CLI output via fast API model.

REQ-4.3.2: CLI output is always summarized via gemini-3-flash-preview.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class OutputSummarizer:
    """
    Summarizes CLI output for return to MCP client.

    Uses gemini-3-flash-preview for speed.
    Only summarizes if output exceeds size threshold.
    """

    model_name: str = "gemini-3-flash-preview"
    tool_name: str = "chat_with_gemini3_flash_preview"
    # Size threshold in characters - only summarize if output is larger
    # Set very high to avoid losing important information from CLI output
    # Summarization is lossy and should only be used for massive outputs
    size_threshold: int = 100_000  # 100KB before summarizing

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
        Summarize CLI output if it exceeds size threshold.

        Args:
            output: Raw CLI output to summarize
            task_context: Optional context about the task

        Returns:
            Summarized output string (or original if under threshold)
        """
        if not output or not output.strip():
            return ""

        # Only summarize if output exceeds threshold
        if len(output) <= self.size_threshold:
            logger.debug(
                f"Output size {len(output)} chars under threshold {self.size_threshold}, "
                "returning verbatim"
            )
            return output

        logger.debug(
            f"Output size {len(output)} chars exceeds threshold {self.size_threshold}, "
            "summarizing via Gemini Flash"
        )

        prompt = self.prompt_template.format(
            output=output,
            context=task_context or "No additional context",
        )

        return await self._call_gemini_flash(prompt)

    async def _call_gemini_flash(self, prompt: str) -> str:
        """Call gemini-3-flash-preview for summarization."""
        from ..tools.registry import get_tool, list_tools
        from ..tools.executor import executor

        # Ensure registry is populated
        list_tools()

        metadata = get_tool(self.tool_name)
        if metadata is None:
            logger.warning(
                f"Tool {self.tool_name} not found, returning truncated output"
            )
            # Fallback: return first 1000 chars if model unavailable
            return prompt[:1000] if len(prompt) > 1000 else prompt

        try:
            response = await executor.execute(
                metadata=metadata,
                instructions=prompt,
                output_format="A concise summary preserving key information",
                session_id=f"summarizer-{id(self)}",
                disable_history_record=True,
                disable_history_search=True,
                timeout=30,  # Quick summarization
            )
            return response or ""
        except Exception as e:
            logger.warning(f"Summarization failed: {e}, returning truncated output")
            # Fallback: return first 1000 chars on error
            return prompt[:1000] if len(prompt) > 1000 else prompt
