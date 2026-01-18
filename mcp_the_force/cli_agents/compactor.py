"""
Compactor: History compaction for cross-tool context injection.

Formats or summarizes conversation history for CLI context limits.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# CLI context limits (approximate, in tokens)
CLI_CONTEXT_LIMITS = {
    "claude": 200_000,
    "gemini": 1_000_000,
    "codex": 128_000,
}


class Compactor:
    """
    Compacts conversation history for CLI context injection.

    When history fits within CLI context limit: formats verbatim.
    When history exceeds limit: summarizes via fast API model.
    """

    def get_context_limit(self, cli_name: str) -> int:
        """Get the context token limit for a CLI."""
        return CLI_CONTEXT_LIMITS.get(cli_name, 100_000)

    def estimate_tokens(self, history: List[Dict[str, Any]]) -> int:
        """
        Estimate token count for conversation history.

        Args:
            history: List of conversation turns

        Returns:
            Estimated token count
        """
        # Rough estimate: 4 chars per token
        total_chars = sum(len(str(turn.get("content", ""))) for turn in history)
        return total_chars // 4

    async def compact_for_cli(
        self,
        history: List[Dict[str, Any]],
        target_cli: str,
        max_tokens: int,
    ) -> str:
        """
        Compact history for injection into a CLI agent.

        Args:
            history: Conversation history to compact
            target_cli: Target CLI name (claude, gemini, codex)
            max_tokens: Maximum tokens for the compacted output

        Returns:
            Formatted or summarized history as a string
        """
        if not history:
            return ""

        # Format history as a context block
        formatted = self._format_history(history)
        estimated_tokens = self.estimate_tokens(history)

        # If it fits, return formatted verbatim
        if estimated_tokens <= max_tokens:
            return f"<context>\n{formatted}\n</context>"

        # Otherwise, summarize
        logger.debug(
            f"History exceeds {max_tokens} tokens ({estimated_tokens}), summarizing"
        )
        summary = await self._call_summarizer(formatted)
        return f"<context>\n{summary}\n</context>"

    def _format_history(self, history: List[Dict[str, Any]]) -> str:
        """Format history as readable text with tool attribution."""
        lines = []
        for turn in history:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            tool = turn.get("tool", "")

            # Add tool attribution if present
            attribution = f" [via {tool}]" if tool else ""
            lines.append(f"[{role.upper()}{attribution}]: {content}")

        return "\n\n".join(lines)

    async def _call_summarizer(self, content: str) -> str:
        """Call the summarization model."""
        from .summarizer import OutputSummarizer

        summarizer = OutputSummarizer()
        return await summarizer.summarize(
            output=content,
            task_context="This is conversation history being summarized for context injection",
        )
