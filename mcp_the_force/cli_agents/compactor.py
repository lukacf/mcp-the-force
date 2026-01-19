"""
Compactor: History compaction for cross-tool context injection.

ALWAYS compacts using Gemini Flash 3 Preview, targeting 30k tokens.
Uses iterative compaction if first pass exceeds target.
"""

import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Compaction settings
COMPACTION_TIMEOUT_SECONDS = 90  # Per compaction attempt
TARGET_TOKENS = 30_000  # Always target this size
MAX_COMPACTION_ROUNDS = 3  # Prevent infinite loops

# Handoff compaction prompt - designed for cross-tool context injection
HANDOFF_COMPACTION_PROMPT = """You are creating a HANDOFF SUMMARY for another AI assistant that will continue this task.

The conversation below occurred with a different AI tool. Your summary will be the ONLY context the next assistant receives, so preserve all critical information needed to continue seamlessly.

**CRITICAL SIZE REQUIREMENT**: Your output MUST be approximately {target_tokens} tokens (~{target_chars} characters). This is NOT optional - the next assistant needs substantial detail to continue effectively. Do NOT over-compress. Include specific details, file paths, code snippets, technical decisions, and error messages where relevant.

CONVERSATION TO SUMMARIZE:
{conversation}

Create a detailed structured handoff summary with these sections:

## User's Goal
What the user originally requested and any clarifications they provided. Be specific about requirements.

## Progress Made
- Key decisions made and their rationale (include WHY)
- Code/files discussed, created, or modified (ALWAYS include full file paths)
- Problems solved or approaches tried (include what failed and why)
- Important technical details, configurations, or patterns used
- Any test results, error messages, or debugging findings

## Current State
Where things stand right now. What's working, what's pending. Be specific about what has been completed vs what remains.

## Next Steps
What should happen next to complete the user's goal. Prioritized and actionable.

## Important Context
- Constraints, preferences, or technical details the next assistant must know
- File paths, variable names, function signatures that are relevant
- Any gotchas, edge cases, or things to avoid
- Project-specific patterns or conventions being followed

**IMPORTANT**: Use the FULL {target_tokens} token budget. Provide detailed, specific information. The next assistant needs enough context to continue without asking the user basic questions. Aim for {target_chars} characters of detailed technical content."""

# Prefix added to compacted context when injecting into new tool
HANDOFF_PREFIX = """[PRIOR CONTEXT: This summary was created from a conversation with a different AI assistant. Use it to continue the user's task without asking them to repeat information.]

"""


class Compactor:
    """
    Compacts conversation history using Gemini Flash 3 Preview.

    ALWAYS compacts (no threshold), targeting 30k tokens.
    Uses iterative re-compaction if first pass is too large.
    """

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count. Rough: 4 chars per token."""
        return len(text) // 4

    async def compact_for_cli(
        self,
        history: List[Dict[str, Any]],
        target_cli: str,
        max_tokens: int,
    ) -> str:
        """
        Compact history for injection into a CLI agent.

        ALWAYS compacts via Gemini Flash, targeting 30k tokens.

        Args:
            history: Conversation history to compact
            target_cli: Target CLI name (for logging)
            max_tokens: Maximum tokens for compacted output (ignored, we use TARGET_TOKENS)

        Returns:
            Compacted history as a string
        """
        if not history:
            return ""

        # Format history
        formatted = self._format_history(history)
        estimated_tokens = self.estimate_tokens(formatted)

        logger.info(
            f"[COMPACTOR] Compacting {len(history)} turns "
            f"(~{estimated_tokens} tokens, {len(formatted)} chars) "
            f"→ target {TARGET_TOKENS} tokens for {target_cli}"
        )

        # ALWAYS compact via Gemini Flash
        compacted = await self._compact_iteratively(formatted)
        result = f"{HANDOFF_PREFIX}{compacted}"

        final_tokens = self.estimate_tokens(compacted)
        logger.info(
            f"[COMPACTOR] Final: {estimated_tokens} → {final_tokens} tokens "
            f"({100 * final_tokens // estimated_tokens}% of original)"
        )

        return result

    async def _compact_iteratively(self, conversation: str) -> str:
        """
        Compact conversation, iterating if result exceeds target.

        Round 1: Compact full conversation → target 30k
        Round 2: If still > target*1.5, compact again
        Round 3: If still > target*1.5, compact again (final attempt)
        """
        current = conversation
        current_tokens = self.estimate_tokens(current)
        compacted = ""  # Initialize to avoid unbound variable

        for round_num in range(1, MAX_COMPACTION_ROUNDS + 1):
            logger.info(
                f"[COMPACTOR] Round {round_num}: compacting ~{current_tokens} tokens"
            )

            compacted = await self._compact_with_handoff_prompt(current)
            compacted_tokens = self.estimate_tokens(compacted)

            logger.info(
                f"[COMPACTOR] Round {round_num} result: "
                f"{current_tokens} → {compacted_tokens} tokens "
                f"({100 * compacted_tokens // current_tokens if current_tokens > 0 else 0}%)"
            )

            # If we're within 1.5x target, we're done
            if compacted_tokens <= TARGET_TOKENS * 1.5:
                logger.info(f"[COMPACTOR] Compaction complete after {round_num} rounds")
                return compacted

            # If this is the last round, return what we have
            if round_num == MAX_COMPACTION_ROUNDS:
                logger.warning(
                    f"[COMPACTOR] Max rounds reached, returning {compacted_tokens} token result "
                    f"(target was {TARGET_TOKENS})"
                )
                return compacted

            # Otherwise, compact again
            current = compacted
            current_tokens = compacted_tokens
            logger.info(
                f"[COMPACTOR] Still too large, running round {round_num + 1}..."
            )

        return compacted

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

    async def _compact_with_handoff_prompt(self, conversation: str) -> str:
        """
        Compact conversation using the specialized handoff prompt.

        Uses Gemini Flash 3 Preview for speed and quality.
        """
        from ..tools.registry import get_tool, list_tools
        from ..tools.executor import executor

        # Ensure registry is populated
        list_tools()

        tool_name = "chat_with_gemini3_flash_preview"
        metadata = get_tool(tool_name)
        if metadata is None:
            logger.error(
                f"[COMPACTOR] Tool {tool_name} not found, falling back to truncation"
            )
            # Fallback: truncate to approximate target
            target_chars = TARGET_TOKENS * 4
            if len(conversation) > target_chars:
                return conversation[:target_chars] + "\n\n[... truncated ...]"
            return conversation

        target_chars = TARGET_TOKENS * 4
        prompt = HANDOFF_COMPACTION_PROMPT.format(
            conversation=conversation,
            target_tokens=TARGET_TOKENS,
            target_chars=target_chars,
        )

        logger.info(
            f"[COMPACTOR] Calling Gemini Flash with {len(prompt)} char prompt "
            f"(timeout={COMPACTION_TIMEOUT_SECONDS}s)"
        )

        start_time = time.time()
        try:
            response = await executor.execute(
                metadata=metadata,
                instructions=prompt,
                output_format="A structured handoff summary in markdown format, targeting the specified size",
                session_id=f"compactor-{id(self)}",
                disable_history_record=True,
                disable_history_search=True,
                timeout=COMPACTION_TIMEOUT_SECONDS,
                reasoning_effort="low",  # Fast compaction, no deep reasoning needed
            )
            elapsed = time.time() - start_time
            response_tokens = self.estimate_tokens(response or "")
            logger.info(
                f"[COMPACTOR] Gemini Flash responded in {elapsed:.2f}s "
                f"(~{response_tokens} tokens)"
            )
            return response or ""
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"[COMPACTOR] Compaction failed after {elapsed:.2f}s: {e}, "
                "falling back to truncation"
            )
            target_chars = TARGET_TOKENS * 4
            if len(conversation) > target_chars:
                return conversation[:target_chars] + "\n\n[... truncated ...]"
            return conversation
