"""
Compactor: History compaction for cross-tool context injection.

Formats or summarizes conversation history for CLI context limits.
"""

from typing import Any, Dict, List


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
        raise NotImplementedError("Compactor.compact_for_cli not implemented")

    async def _call_summarizer(self, content: str) -> str:
        """Call the summarization model."""
        raise NotImplementedError("Compactor._call_summarizer not implemented")
