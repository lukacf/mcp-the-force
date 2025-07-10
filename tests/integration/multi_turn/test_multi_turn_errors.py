"""Integration tests for multi-turn error cases and regressions.

These tests verify error handling and catch regression of the bugs we fixed.
"""

import pytest
import json
from unittest.mock import patch
from mcp_second_brain.tools.executor import executor
from mcp_second_brain.tools.registry import get_tool
from mcp_second_brain.adapters import get_adapter


class TestMultiTurnErrors:
    """Test error cases and regression scenarios."""

    @pytest.mark.asyncio
    async def test_regression_session_id_not_passed_to_adapter(
        self, clean_session_caches
    ):
        """Regression test: Ensure session_id is always passed to adapters.

        This test would have caught the bug where session parameters weren't
        merged into adapter parameters.
        """
        metadata = get_tool("chat_with_gemini25_pro")

        # Track what parameters reach the adapter
        adapter_calls = []

        # Patch adapter to capture calls

        async def track_generate(self, prompt, **kwargs):
            adapter_calls.append(kwargs)
            return json.dumps({"prompt": prompt, "adapter_kwargs": kwargs, "tools": []})

        with patch.object(
            type(get_adapter(metadata.model_config)), "generate", track_generate
        ):
            # Execute with session_id
            await executor.execute(
                metadata,
                instructions="Test",
                output_format="Test",
                context=[],
                session_id="test-session-123",
            )

            # Verify session_id reached the adapter
            assert len(adapter_calls) == 1
            assert (
                "session_id" in adapter_calls[0]
            ), "Bug: session_id not passed to adapter!"
            assert adapter_calls[0]["session_id"] == "test-session-123"

    @pytest.mark.asyncio
    async def test_regression_system_instruction_missing_on_later_turns(
        self, clean_session_caches, session_id_generator
    ):
        """Regression test: Ensure system_instruction sent on ALL turns.

        This test would have caught the bug where system_instruction was
        only sent on first turn (when no session_id).
        """
        metadata = get_tool("chat_with_gemini25_pro")
        session_id = session_id_generator()

        # Track adapter calls
        adapter_calls = []

        async def track_generate(self, prompt, **kwargs):
            adapter_calls.append(kwargs)
            return json.dumps({"prompt": prompt, "adapter_kwargs": kwargs, "tools": []})

        with patch.object(
            type(get_adapter(metadata.model_config)), "generate", track_generate
        ):
            # First turn
            await executor.execute(
                metadata,
                instructions="First message",
                output_format="OK",
                context=[],
                session_id=session_id,
            )

            # Second turn
            await executor.execute(
                metadata,
                instructions="Second message",
                output_format="OK",
                context=[],
                session_id=session_id,
            )

            # Both calls should have system_instruction
            assert len(adapter_calls) == 2
            assert (
                "system_instruction" in adapter_calls[0]
            ), "First turn missing system_instruction"
            assert (
                "system_instruction" in adapter_calls[1]
            ), "Bug: Second turn missing system_instruction!"

            # Verify it contains priority instructions
            instruction = adapter_calls[1]["system_instruction"]
            assert "Information priority order:" in instruction

    @pytest.mark.asyncio
    async def test_model_uses_search_without_proper_prompt(
        self, clean_session_caches, track_tool_calls, session_id_generator
    ):
        """Test that models use search if system prompt doesn't guide them.

        This simulates the bug where models used search_project_memory
        instead of conversation history.
        """
        metadata = get_tool("chat_with_gemini25_pro")
        session_id = session_id_generator()

        # Override system instruction to old version
        old_prompt = "Use the available tools whenever you need additional context"

        with patch(
            "mcp_second_brain.prompts.get_developer_prompt", return_value=old_prompt
        ):
            # First turn
            await executor.execute(
                metadata,
                instructions="Remember: The secret code is ALPHA",
                output_format="OK",
                context=[],
                session_id=session_id,
            )

            # Reset tool tracking
            track_tool_calls.clear()

            # Second turn - with bad prompt, model might use search
            result = await executor.execute(
                metadata,
                instructions="What's the secret code?",
                output_format="Tell me",
                context=[],
                session_id=session_id,
            )

            # With old prompt, model might search (this is the bug we fixed)
            # With new prompt, it should use conversation history
            data = json.loads(result)

            # Verify the prompt guides model correctly
            if (
                "Information priority order:"
                not in data["adapter_kwargs"]["system_instruction"]
            ):
                # Old prompt - model might search
                assert old_prompt in data["adapter_kwargs"]["system_instruction"]

    @pytest.mark.asyncio
    async def test_cross_model_sessions_isolated(
        self, clean_session_caches, session_id_generator
    ):
        """Test that sessions are isolated between different model types."""
        # Same session ID, different models
        session_id = session_id_generator()

        # Gemini: Store fact A
        gemini_meta = get_tool("chat_with_gemini25_pro")
        await executor.execute(
            gemini_meta,
            instructions="Gemini fact: Earth has one moon",
            output_format="OK",
            context=[],
            session_id=session_id,
        )

        # Grok: Store fact B (same session ID)
        grok_meta = get_tool("chat_with_grok4")
        await executor.execute(
            grok_meta,
            instructions="Grok fact: Mars has two moons",
            output_format="OK",
            context=[],
            session_id=session_id,
        )

        # Query Gemini - should only know its fact
        gemini_result = await executor.execute(
            gemini_meta,
            instructions="What facts do you know about moons?",
            output_format="List facts",
            context=[],
            session_id=session_id,
        )

        gemini_data = json.loads(gemini_result)
        assert "Earth has one moon" in gemini_data["prompt"]
        assert "Mars has two moons" not in gemini_data["prompt"]

        # Query Grok - should only know its fact
        grok_result = await executor.execute(
            grok_meta,
            instructions="What facts do you know about moons?",
            output_format="List facts",
            context=[],
            session_id=session_id,
        )

        grok_data = json.loads(grok_result)
        assert "Mars has two moons" in grok_data["prompt"]
        assert "Earth has one moon" not in grok_data["prompt"]

    @pytest.mark.asyncio
    async def test_empty_session_id_rejected(self, clean_session_caches):
        """Test that empty session_id is handled properly."""
        metadata = get_tool("chat_with_gemini25_pro")

        # Empty string session_id
        with pytest.raises(Exception) as exc_info:
            await executor.execute(
                metadata,
                instructions="Test",
                output_format="Test",
                context=[],
                session_id="",  # Empty!
            )

        # Should fail validation
        assert "session_id" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_concurrent_sessions_no_crosstalk(
        self, clean_session_caches, session_id_generator
    ):
        """Test that concurrent sessions don't interfere with each other."""
        import asyncio

        metadata = get_tool("chat_with_gemini25_pro")

        async def session_flow(session_num: int):
            session_id = f"concurrent-{session_num}"

            # Store unique fact
            await executor.execute(
                metadata,
                instructions=f"Session {session_num}: Remember number {session_num * 100}",
                output_format="OK",
                context=[],
                session_id=session_id,
            )

            # Small delay to ensure concurrency
            await asyncio.sleep(0.1)

            # Recall fact
            result = await executor.execute(
                metadata,
                instructions="What number should you remember?",
                output_format="State the number",
                context=[],
                session_id=session_id,
            )

            data = json.loads(result)
            expected = str(session_num * 100)
            assert expected in data["prompt"], f"Session {session_num} lost its data!"

            # Ensure no crosstalk
            for other in range(1, 6):
                if other != session_num:
                    other_num = str(other * 100)
                    assert (
                        other_num not in data["prompt"]
                    ), f"Session {session_num} has data from session {other}!"

        # Run 5 concurrent sessions
        await asyncio.gather(*[session_flow(i) for i in range(1, 6)])
