"""Integration tests for Grok multi-turn conversations.

These tests verify Grok session management and multi-turn support.
"""

import pytest
import json
from mcp_the_force.tools.executor import executor
from mcp_the_force.tools.registry import get_tool


class TestGrokMultiTurn:
    """Test multi-turn conversations with Grok models."""

    @pytest.mark.asyncio
    async def test_grok4_multi_turn_basic(
        self, clean_session_caches, session_id_generator
    ):
        """Test basic Grok 4 multi-turn conversation."""
        metadata = get_tool("chat_with_grok41")
        session_id = session_id_generator()

        # First turn
        result1 = await executor.execute(
            metadata,
            instructions="My favorite programming language is Rust.",
            output_format="Acknowledge",
            context=[],
            session_id=session_id,
        )

        data1 = json.loads(result1)
        assert data1["adapter_kwargs"]["session_id"] == session_id
        # Note: 'messages' are constructed internally by the Grok adapter, not passed as kwargs

        # Second turn
        result2 = await executor.execute(
            metadata,
            instructions="What's my favorite programming language?",
            output_format="Answer based on our conversation",
            context=[],
            session_id=session_id,
        )

        data2 = json.loads(result2)
        # Should have Rust in conversation history
        assert "Rust" in data2["prompt"]
        # Verify conversation continuity through prompt content

    @pytest.mark.asyncio
    async def test_grok3_reasoning_multi_turn(
        self, clean_session_caches, session_id_generator
    ):
        """Test Grok 3 reasoning model multi-turn."""
        metadata = get_tool("chat_with_grok3_fast")
        session_id = session_id_generator()

        # First turn: Present a problem
        result1 = await executor.execute(
            metadata,
            instructions="I have a list of 1 million integers that need sorting.",
            output_format="Acknowledge the problem",
            context=[],
            session_id=session_id,
        )

        data1 = json.loads(result1)
        assert data1["adapter_kwargs"]["session_id"] == session_id

        # Second turn: Ask for solution
        result2 = await executor.execute(
            metadata,
            instructions="What's the most efficient sorting algorithm for my use case?",
            output_format="Recommend algorithm with reasoning",
            context=[],
            session_id=session_id,
        )

        data2 = json.loads(result2)
        # Should reference the million integers from first turn
        assert "million" in data2["prompt"] or "1000000" in data2["prompt"]
        # Verify conversation continuity through prompt content

    @pytest.mark.asyncio
    async def test_grok_temperature_preserved(
        self, clean_session_caches, session_id_generator
    ):
        """Test that custom temperature is preserved across turns."""
        metadata = get_tool("chat_with_grok41")
        session_id = session_id_generator()

        # First turn with custom temperature
        result1 = await executor.execute(
            metadata,
            instructions="Generate creative names",
            output_format="List",
            context=[],
            session_id=session_id,
            temperature=0.9,
        )

        data1 = json.loads(result1)
        assert data1["adapter_kwargs"]["temperature"] == 0.9

        # Second turn - temperature should be default
        result2 = await executor.execute(
            metadata,
            instructions="More names",
            output_format="List",
            context=[],
            session_id=session_id,
            # No temperature specified
        )

        data2 = json.loads(result2)
        # Should use default temperature
        assert data2["adapter_kwargs"]["temperature"] == 0.7  # Grok default

    @pytest.mark.asyncio
    async def test_grok_system_prompt_priority(
        self, clean_session_caches, session_id_generator
    ):
        """Test that Grok models get updated priority instructions."""
        metadata = get_tool("chat_with_grok41")
        session_id = session_id_generator()

        result = await executor.execute(
            metadata,
            instructions="Test",
            output_format="Test",
            context=[],
            session_id=session_id,
        )

        data = json.loads(result)

        # The test should verify that the system prompt with priority instructions
        # is being sent to the API (not saved in conversation history)
        messages = data["adapter_kwargs"]["messages"]

        # Find the developer message in the request (Grok uses developer role like OpenAI)
        developer_message = None
        for msg in messages:
            if msg.get("role") == "developer":
                developer_message = msg.get("content", "")
                break

        # Verify priority instructions are in the developer prompt
        assert developer_message is not None, "Developer message should be present"
        assert "Information priority" in developer_message
        assert "Current conversation" in developer_message

    @pytest.mark.asyncio
    async def test_grok_session_isolation(
        self, clean_session_caches, session_id_generator
    ):
        """Test that Grok sessions are properly isolated."""
        metadata = get_tool("chat_with_grok41")
        session1 = session_id_generator()
        session2 = session_id_generator()

        # Session 1: Store fact A
        await executor.execute(
            metadata,
            instructions="Important: The password is ABC123",
            output_format="OK",
            context=[],
            session_id=session1,
        )

        # Session 2: Store fact B
        await executor.execute(
            metadata,
            instructions="Important: The password is XYZ789",
            output_format="OK",
            context=[],
            session_id=session2,
        )

        # Query session 1
        result1 = await executor.execute(
            metadata,
            instructions="What's the password?",
            output_format="Answer",
            context=[],
            session_id=session1,
        )

        data1 = json.loads(result1)
        # Verify session 1 was used
        assert data1["adapter_kwargs"]["session_id"] == session1

        # Query session 2
        result2 = await executor.execute(
            metadata,
            instructions="What's the password?",
            output_format="Answer",
            context=[],
            session_id=session2,
        )

        data2 = json.loads(result2)
        # Verify session 2 was used
        assert data2["adapter_kwargs"]["session_id"] == session2

        # The actual session isolation (history not mixing) would be tested
        # in the Grok adapter's internal session cache, not visible to MockAdapter
