"""
Unit Tests: Compactor.

Tests history compaction logic in isolation.
"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.xfail(
    reason="Phase 2: Compactor not yet implemented", raises=NotImplementedError
)
class TestCompactor:
    """Unit tests for Compactor."""

    @pytest.mark.asyncio
    async def test_formats_small_history_verbatim(self):
        """Compactor returns history as-is when within token limit."""
        from mcp_the_force.cli_agents.compactor import Compactor

        history = [
            {"role": "user", "content": "Short message"},
            {"role": "assistant", "content": "Short reply"},
        ]

        compactor = Compactor()
        result = await compactor.compact_for_cli(
            history=history,
            target_cli="claude",
            max_tokens=8000,
        )

        assert "Short message" in result
        assert "Short reply" in result

    @pytest.mark.asyncio
    async def test_summarizes_large_history(self):
        """Compactor summarizes history when exceeds token limit."""
        from mcp_the_force.cli_agents.compactor import Compactor

        # Create history that exceeds limits
        large_history = [
            {"role": "user", "content": f"Message {i}: " + "x" * 500} for i in range(50)
        ]

        compactor = Compactor()

        # Mock the summarization call
        with patch.object(
            compactor, "_call_summarizer", new_callable=AsyncMock
        ) as mock_summarize:
            mock_summarize.return_value = "Summarized: User discussed 50 topics"

            result = await compactor.compact_for_cli(
                history=large_history,
                target_cli="claude",
                max_tokens=1000,  # Force summarization
            )

            mock_summarize.assert_called_once()
            assert "Summarized" in result

    @pytest.mark.asyncio
    async def test_respects_cli_specific_limits(self):
        """Compactor uses CLI-specific token limits."""
        from mcp_the_force.cli_agents.compactor import Compactor

        compactor = Compactor()

        # Different CLIs have different context limits
        claude_limit = compactor.get_context_limit("claude")
        gemini_limit = compactor.get_context_limit("gemini")
        codex_limit = compactor.get_context_limit("codex")

        # Gemini has larger context than Claude/Codex
        assert gemini_limit >= claude_limit
        assert codex_limit <= claude_limit  # Codex is more limited

    @pytest.mark.asyncio
    async def test_formats_as_xml_context_block(self):
        """Compactor formats output as XML context block."""
        from mcp_the_force.cli_agents.compactor import Compactor

        history = [
            {"role": "user", "content": "Design auth"},
            {"role": "assistant", "content": "JWT approach"},
        ]

        compactor = Compactor()
        result = await compactor.compact_for_cli(
            history=history,
            target_cli="claude",
            max_tokens=8000,
        )

        # Should be formatted as context block
        assert "<context>" in result or "CONTEXT" in result.upper()

    @pytest.mark.asyncio
    async def test_preserves_tool_attribution(self):
        """Compactor preserves which tool generated each message."""
        from mcp_the_force.cli_agents.compactor import Compactor

        history = [
            {"role": "user", "content": "Question", "tool": "work_with"},
            {"role": "assistant", "content": "Answer from Claude", "tool": "work_with"},
            {"role": "user", "content": "Follow up", "tool": "chat_with_gpt52"},
            {
                "role": "assistant",
                "content": "Answer from GPT",
                "tool": "chat_with_gpt52",
            },
        ]

        compactor = Compactor()
        result = await compactor.compact_for_cli(
            history=history,
            target_cli="gemini",
            max_tokens=8000,
        )

        # Should indicate tool source when relevant
        assert "Claude" in result or "GPT" in result or "work_with" in result


class TestTokenEstimation:
    """Unit tests for token counting in Compactor."""

    def test_estimates_tokens_for_history(self):
        """Compactor estimates token count for history."""
        from mcp_the_force.cli_agents.compactor import Compactor

        history = [
            {"role": "user", "content": "Hello world"},
        ]

        compactor = Compactor()
        tokens = compactor.estimate_tokens(history)

        # "Hello world" ≈ 2-3 tokens, plus role overhead
        assert tokens > 0
        assert tokens < 100

    def test_token_estimation_scales_with_content(self):
        """Compactor token estimation scales with content length."""
        from mcp_the_force.cli_agents.compactor import Compactor

        small_history = [{"role": "user", "content": "Hi"}]
        large_history = [{"role": "user", "content": "x" * 1000}]

        compactor = Compactor()
        small_tokens = compactor.estimate_tokens(small_history)
        large_tokens = compactor.estimate_tokens(large_history)

        assert large_tokens > small_tokens
