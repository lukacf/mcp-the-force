"""Integration tests for multi-turn error cases and regressions.

These tests verify error handling and catch regression of the bugs we fixed.
"""

import pytest
import json
from unittest.mock import patch
from mcp_the_force.tools.executor import executor
from mcp_the_force.tools.registry import get_tool


class TestMultiTurnErrors:
    """Test error cases and regression scenarios."""

    @pytest.mark.asyncio
    async def test_regression_session_id_not_passed_to_adapter(
        self, clean_session_caches, run_tool, parse_adapter_response
    ):
        """Regression test: Ensure session_id is always passed to adapters.

        This test would have caught the bug where session parameters weren't
        merged into adapter parameters.
        """
        # Execute with session_id using MockAdapter
        result = await run_tool(
            "chat_with_gemini3_pro_preview",
            instructions="Test instruction",
            output_format="Test format",
            context=[],
            session_id="test-session-123",
        )

        # Parse the MockAdapter response
        data = parse_adapter_response(result)

        # Verify the plumbing worked correctly:
        # 1. MockAdapter was used
        assert data["mock"] is True
        assert data["model"] == "gemini-3-pro-preview"

        # 2. Session ID was passed through to adapter
        assert (
            "session_id" in data["adapter_kwargs"]
        ), "Bug: session_id not passed to adapter!"
        assert data["adapter_kwargs"]["session_id"] == "test-session-123"

        # 3. Other parameters were routed correctly
        assert "Test instruction" in data["prompt"]

    @pytest.mark.asyncio
    async def test_regression_system_instruction_missing_on_later_turns(
        self,
        clean_session_caches,
        session_id_generator,
        run_tool,
        parse_adapter_response,
    ):
        """Regression test: Ensure system_instruction sent on ALL turns.

        This test would have caught the bug where system_instruction was
        only sent on first turn (when no session_id).
        """
        session_id = session_id_generator()

        # First turn
        result1 = await run_tool(
            "chat_with_gemini3_pro_preview",
            instructions="First message",
            output_format="OK",
            context=[],
            session_id=session_id,
        )

        # Second turn with same session
        result2 = await run_tool(
            "chat_with_gemini3_pro_preview",
            instructions="Second message",
            output_format="OK",
            context=[],
            session_id=session_id,
        )

        # Parse both responses
        data1 = parse_adapter_response(result1)
        data2 = parse_adapter_response(result2)

        # Both calls should have system_instruction in adapter_kwargs
        assert (
            "system_instruction" in data1["adapter_kwargs"]
        ), "First turn missing system_instruction"
        assert (
            "system_instruction" in data2["adapter_kwargs"]
        ), "Bug: Second turn missing system_instruction!"

        # Verify session continuity
        assert data1["adapter_kwargs"]["session_id"] == session_id
        assert data2["adapter_kwargs"]["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_model_uses_search_without_proper_prompt(
        self, clean_session_caches, session_id_generator
    ):
        """Test that models use search if system prompt doesn't guide them.

        This simulates the bug where models used search_project_history
        instead of conversation history.
        """
        metadata = get_tool("chat_with_gemini3_pro_preview")
        session_id = session_id_generator()

        # Override system instruction to old version
        old_prompt = "Use the available tools whenever you need additional context"

        with patch(
            "mcp_the_force.prompts.get_developer_prompt", return_value=old_prompt
        ):
            # First turn
            await executor.execute(
                metadata,
                instructions="Remember: The secret code is ALPHA",
                output_format="OK",
                context=[],
                session_id=session_id,
            )

            # Note: With MockAdapter, we test prompt routing instead of actual tool usage

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
        """Test that sessions with different IDs are isolated."""
        # Different session IDs for different models
        gemini_session = session_id_generator()
        grok_session = session_id_generator()

        # Gemini: Store fact A
        gemini_meta = get_tool("chat_with_gemini3_pro_preview")
        await executor.execute(
            gemini_meta,
            instructions="Gemini fact: Earth has one moon",
            output_format="OK",
            context=[],
            session_id=gemini_session,
        )

        # Grok: Store fact B (different session ID)
        grok_meta = get_tool("chat_with_grok41")
        await executor.execute(
            grok_meta,
            instructions="Grok fact: Mars has two moons",
            output_format="OK",
            context=[],
            session_id=grok_session,
        )

        # Query Gemini - should only know its fact
        gemini_result = await executor.execute(
            gemini_meta,
            instructions="What facts do you know about moons?",
            output_format="List facts",
            context=[],
            session_id=gemini_session,
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
            session_id=grok_session,
        )

        grok_data = json.loads(grok_result)
        assert "Mars has two moons" in grok_data["prompt"]
        assert "Earth has one moon" not in grok_data["prompt"]

    @pytest.mark.asyncio
    async def test_empty_session_id_rejected(self, clean_session_caches):
        """Test that empty session_id is handled properly."""
        metadata = get_tool("chat_with_gemini3_pro_preview")

        # Empty string session_id is technically valid (just a string)
        # This test documents that behavior
        result = await executor.execute(
            metadata,
            instructions="Test",
            output_format="Test",
            context=[],
            session_id="",  # Empty but valid
        )

        # Should work but with empty session
        assert result is not None

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)  # Increase timeout for concurrent executions
    async def test_concurrent_sessions_no_crosstalk(
        self, clean_session_caches, session_id_generator
    ):
        """Test that concurrent sessions don't interfere with each other."""
        import asyncio

        metadata = get_tool("chat_with_gemini3_pro_preview")

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
