"""
Unit Tests: Compactor.

Tests history compaction logic in isolation.
"""

import pytest
from unittest.mock import AsyncMock, patch


class TestCompactor:
    """Unit tests for Compactor."""

    @pytest.mark.asyncio
    async def test_formats_small_history_verbatim(self):
        """Compactor includes history content when within reasonable size."""
        from mcp_the_force.cli_agents.compactor import Compactor

        history = [
            {"role": "user", "content": "Short message"},
            {"role": "assistant", "content": "Short reply"},
        ]

        compactor = Compactor()

        # Mock the compaction call to return formatted content
        with patch.object(
            compactor, "_compact_with_handoff_prompt", new_callable=AsyncMock
        ) as mock_compact:
            mock_compact.return_value = (
                "User asked: Short message. Assistant replied: Short reply"
            )

            result = await compactor.compact_for_cli(
                history=history,
                target_cli="claude",
                max_tokens=8000,
            )

            # Should include the compacted content
            assert "Short message" in result or "PRIOR CONTEXT" in result

    @pytest.mark.asyncio
    async def test_summarizes_large_history(self):
        """Compactor summarizes history via Gemini Flash."""
        from mcp_the_force.cli_agents.compactor import Compactor

        # Create history that exceeds limits
        large_history = [
            {"role": "user", "content": f"Message {i}: " + "x" * 500} for i in range(50)
        ]

        compactor = Compactor()

        # Mock the compaction call
        with patch.object(
            compactor, "_compact_with_handoff_prompt", new_callable=AsyncMock
        ) as mock_compact:
            mock_compact.return_value = "Summarized: User discussed 50 topics"

            result = await compactor.compact_for_cli(
                history=large_history,
                target_cli="claude",
                max_tokens=1000,
            )

            mock_compact.assert_called()
            assert "Summarized" in result

    @pytest.mark.asyncio
    async def test_always_targets_30k_tokens(self):
        """Compactor always targets 30k tokens regardless of max_tokens arg."""
        from mcp_the_force.cli_agents.compactor import TARGET_TOKENS

        assert TARGET_TOKENS == 30_000

    @pytest.mark.asyncio
    async def test_formats_output_with_handoff_prefix(self):
        """Compactor formats output with PRIOR CONTEXT prefix."""
        from mcp_the_force.cli_agents.compactor import Compactor

        history = [
            {"role": "user", "content": "Design auth"},
            {"role": "assistant", "content": "JWT approach"},
        ]

        compactor = Compactor()

        with patch.object(
            compactor, "_compact_with_handoff_prompt", new_callable=AsyncMock
        ) as mock_compact:
            mock_compact.return_value = "Summary of auth discussion"

            result = await compactor.compact_for_cli(
                history=history,
                target_cli="claude",
                max_tokens=8000,
            )

            # Should include handoff prefix
            assert "PRIOR CONTEXT" in result

    @pytest.mark.asyncio
    async def test_preserves_tool_attribution(self):
        """Compactor preserves which tool generated each message in formatted history."""
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

        # Test the internal formatting
        formatted = compactor._format_history(history)

        # Should indicate tool source
        assert "work_with" in formatted or "chat_with_gpt52" in formatted


class TestTokenEstimation:
    """Unit tests for token counting in Compactor."""

    def test_estimates_tokens_for_text(self):
        """Compactor estimates token count for text strings."""
        from mcp_the_force.cli_agents.compactor import Compactor

        text = "Hello world this is a test"

        compactor = Compactor()
        tokens = compactor.estimate_tokens(text)

        # ~4 chars per token, "Hello world this is a test" = 26 chars ≈ 6-7 tokens
        assert tokens > 0
        assert tokens < 100

    def test_token_estimation_scales_with_content(self):
        """Compactor token estimation scales with content length."""
        from mcp_the_force.cli_agents.compactor import Compactor

        small_text = "Hi"
        large_text = "x" * 1000

        compactor = Compactor()
        small_tokens = compactor.estimate_tokens(small_text)
        large_tokens = compactor.estimate_tokens(large_text)

        assert large_tokens > small_tokens

    def test_estimates_roughly_4_chars_per_token(self):
        """Token estimation uses ~4 chars per token heuristic."""
        from mcp_the_force.cli_agents.compactor import Compactor

        # 400 chars should be ~100 tokens
        text = "a" * 400

        compactor = Compactor()
        tokens = compactor.estimate_tokens(text)

        assert tokens == 100  # 400 // 4 = 100
