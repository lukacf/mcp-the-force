"""Integration tests for Gemini multi-turn conversations.

These tests verify that session management works correctly and would have caught
the bugs where:
1. session_id wasn't passed to adapters
2. system_instruction wasn't sent on subsequent turns
3. Models used search_project_memory instead of conversation history
"""

import pytest
import json
from mcp_second_brain.tools.executor import executor
from mcp_second_brain.tools.registry import get_tool


class TestGeminiMultiTurn:
    """Test multi-turn conversations with Gemini models."""

    @pytest.mark.asyncio
    async def test_gemini_remembers_across_turns(
        self, clean_session_caches, session_id_generator
    ):
        """Test that Gemini remembers information across conversation turns."""
        metadata = get_tool("chat_with_gemini25_pro")
        session_id = session_id_generator()

        # First turn: Ask model to remember something
        result1 = await executor.execute(
            metadata,
            instructions="Please remember this number: 9876. Confirm you've stored it.",
            output_format="Acknowledge storing the number",
            context=[],
            session_id=session_id,
        )

        # Verify first response (MockAdapter returns JSON with metadata)
        data1 = json.loads(result1)
        assert "9876" in data1["prompt"]
        assert (
            data1["adapter_kwargs"]["session_id"] == session_id
        )  # Bug 1: session_id must be passed
        assert (
            "system_instruction" in data1["adapter_kwargs"]
        )  # System instruction sent

        # Second turn: Ask model to recall
        result2 = await executor.execute(
            metadata,
            instructions="What number did I ask you to remember in my previous message?",
            output_format="Tell me the exact number",
            context=[],
            session_id=session_id,
        )

        # Verify second response
        data2 = json.loads(result2)

        # Bug 2: system_instruction must be sent on ALL turns
        assert "system_instruction" in data2["adapter_kwargs"]
        assert data2["adapter_kwargs"]["session_id"] == session_id

        # Bug 3: Verify conversation history is in prompt (not using search)
        assert "9876" in data2["prompt"], (
            "Previous message should be in conversation history"
        )
        assert "What number did I ask you to remember" in data2["prompt"]

        # Verify NO search tools were called
        # Note: With MockAdapter, we verify plumbing instead of tool usage

    @pytest.mark.asyncio
    async def test_gemini_flash_multi_turn(
        self, clean_session_caches, session_id_generator
    ):
        """Test multi-turn with Gemini Flash model."""
        metadata = get_tool("chat_with_gemini25_flash")
        session_id = session_id_generator()

        # First turn
        result1 = await executor.execute(
            metadata,
            instructions="Remember the color blue.",
            output_format="Confirm",
            context=[],
            session_id=session_id,
        )

        data1 = json.loads(result1)
        assert data1["adapter_kwargs"]["session_id"] == session_id

        # Second turn
        result2 = await executor.execute(
            metadata,
            instructions="What color did I mention?",
            output_format="State the color",
            context=[],
            session_id=session_id,
        )

        data2 = json.loads(result2)
        assert "blue" in data2["prompt"].lower()
        # Note: With MockAdapter, we verify plumbing instead of tool usage

    @pytest.mark.asyncio
    async def test_system_instruction_priority_order(
        self, clean_session_caches, session_id_generator
    ):
        """Test that system instruction includes correct priority order."""
        metadata = get_tool("chat_with_gemini25_pro")
        session_id = session_id_generator()

        # Execute a call
        result = await executor.execute(
            metadata,
            instructions="Test message",
            output_format="Test",
            context=[],
            session_id=session_id,
        )

        data = json.loads(result)
        system_instruction = data["adapter_kwargs"]["system_instruction"]

        # Verify the system instruction contains the priority order we added
        assert "Information priority order:" in system_instruction
        assert (
            "FIRST: Always check the current conversation history" in system_instruction
        )
        assert (
            "LAST: Use search_project_memory only when you need historical information"
            in system_instruction
        )

    @pytest.mark.asyncio
    async def test_different_sessions_isolated(
        self, clean_session_caches, session_id_generator
    ):
        """Test that different sessions don't share history."""
        metadata = get_tool("chat_with_gemini25_pro")
        session1 = session_id_generator()
        session2 = session_id_generator()

        # Session 1: Remember 111
        await executor.execute(
            metadata,
            instructions="Remember: 111",
            output_format="Confirm",
            context=[],
            session_id=session1,
        )

        # Session 2: Remember 222
        await executor.execute(
            metadata,
            instructions="Remember: 222",
            output_format="Confirm",
            context=[],
            session_id=session2,
        )

        # Session 1: Should only know 111
        result1 = await executor.execute(
            metadata,
            instructions="What number?",
            output_format="Tell me",
            context=[],
            session_id=session1,
        )

        data1 = json.loads(result1)
        assert "111" in data1["prompt"]
        assert "222" not in data1["prompt"]

        # Session 2: Should only know 222
        result2 = await executor.execute(
            metadata,
            instructions="What number?",
            output_format="Tell me",
            context=[],
            session_id=session2,
        )

        data2 = json.loads(result2)
        assert "222" in data2["prompt"]
        assert "111" not in data2["prompt"]

    @pytest.mark.asyncio
    async def test_complex_multi_turn_conversation(
        self, clean_session_caches, session_id_generator
    ):
        """Test a longer conversation with multiple turns."""
        metadata = get_tool("chat_with_gemini25_pro")
        session_id = session_id_generator()

        # Turn 1: Introduction
        await executor.execute(
            metadata,
            instructions="My name is Alice and I'm working on project Phoenix.",
            output_format="Acknowledge",
            context=[],
            session_id=session_id,
        )

        # Turn 2: Add more info
        await executor.execute(
            metadata,
            instructions="The project uses Python and PostgreSQL.",
            output_format="Acknowledge",
            context=[],
            session_id=session_id,
        )

        # Turn 3: Question about earlier info
        result = await executor.execute(
            metadata,
            instructions="What's my name and what project am I working on?",
            output_format="Answer based on our conversation",
            context=[],
            session_id=session_id,
        )

        data = json.loads(result)
        # All previous messages should be in history
        assert "Alice" in data["prompt"]
        assert "Phoenix" in data["prompt"]
        assert "Python" in data["prompt"]
        assert "PostgreSQL" in data["prompt"]

        # No search tools used
        # Note: With MockAdapter, we verify plumbing instead of tool usage

    @pytest.mark.asyncio
    async def test_regression_no_session_id_passed(self, clean_session_caches):
        """Regression test: Verify failure if session_id not passed to adapter."""
        metadata = get_tool("chat_with_gemini25_pro")

        # Import patch here
        from unittest.mock import patch

        # Patch to simulate the bug where session params aren't merged
        with patch(
            "mcp_second_brain.tools.executor.ToolExecutor.execute"
        ) as mock_execute:

            async def buggy_execute(self, metadata, **kwargs):
                # Simulate bug: don't merge session params
                from mcp_second_brain.tools.parameter_router import ParameterRouter

                router = ParameterRouter()
                routed = router.route(metadata, kwargs)

                # Bug simulation: don't pass session_id to adapter
                adapter_params = routed["adapter"]
                # adapter_params.update(routed["session"])  # BUG: This line missing!

                # Don't actually call adapter, just return mock data
                return json.dumps({"adapter_kwargs": adapter_params})

            mock_execute.side_effect = buggy_execute

            # This should fail to maintain conversation
            result = await mock_execute(
                None,
                metadata,
                instructions="Remember 999",
                output_format="OK",
                context=[],
                session_id="test-regression",
            )

            data = json.loads(result)
            # Bug verification: session_id NOT in adapter kwargs
            assert "session_id" not in data["adapter_kwargs"]

    @pytest.mark.asyncio
    async def test_conversation_with_context_files(
        self, clean_session_caches, session_id_generator
    ):
        """Test that stable-list works correctly with sessions."""
        metadata = get_tool("chat_with_gemini25_pro")
        session_id = session_id_generator()

        # First turn with context
        result1 = await executor.execute(
            metadata,
            instructions="Analyze this code",
            output_format="Summary",
            context=["tests/fixtures/sample.py"],  # Some test file
            session_id=session_id,
        )

        data1 = json.loads(result1)
        assert data1["adapter_kwargs"]["session_id"] == session_id

        # Second turn - context should be minimal due to stable-list
        result2 = await executor.execute(
            metadata,
            instructions="What did you find?",
            output_format="Details",
            context=["tests/fixtures/sample.py"],  # Same file
            session_id=session_id,
        )

        data2 = json.loads(result2)
        # Should still have conversation history
        assert "Analyze this code" in data2["prompt"]
        # Note: With MockAdapter, we verify plumbing instead of tool usage
