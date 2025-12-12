"""Integration tests for OpenAI multi-turn conversations.

These tests verify session management with response IDs and multi-turn support.
"""

import pytest
import json
from mcp_the_force.tools.executor import executor
from mcp_the_force.tools.registry import get_tool


class TestOpenAIMultiTurn:
    """Test multi-turn conversations with OpenAI models."""

    @pytest.mark.asyncio
    async def test_o3_multi_turn_with_response_ids(
        self, clean_session_caches, session_id_generator
    ):
        """Test that o3 maintains conversation across turns."""
        metadata = get_tool("chat_with_gpt52_pro")
        session_id = session_id_generator()

        # First turn
        result1 = await executor.execute(
            metadata,
            instructions="Remember this fact: The sky is blue.",
            output_format="Acknowledge",
            context=[],
            session_id=session_id,
        )

        data1 = json.loads(result1)
        assert data1["adapter_kwargs"]["session_id"] == session_id
        assert "messages" in data1["adapter_kwargs"]  # OpenAI uses messages format
        assert data1["turn_count"] == 1

        # Second turn
        result2 = await executor.execute(
            metadata,
            instructions="What fact did I tell you?",
            output_format="State the fact",
            context=[],
            session_id=session_id,
        )

        data2 = json.loads(result2)
        assert data2["adapter_kwargs"]["session_id"] == session_id
        assert data2["turn_count"] == 2  # Conversation history maintained

        # Check that conversation history contains both turns
        assert "Remember this fact: The sky is blue" in data2["conversation"]
        assert "What fact did I tell you?" in data2["conversation"]

        # Verify messages format for OpenAI
        messages = data2["adapter_kwargs"]["messages"]
        assert len(messages) >= 2  # At least user messages from both turns

    @pytest.mark.asyncio
    async def test_o3_pro_multi_turn(self, clean_session_caches, session_id_generator):
        """Test o3-pro multi-turn with deep reasoning."""
        metadata = get_tool("chat_with_gpt52_pro")
        session_id = session_id_generator()

        # First turn: Complex problem
        result1 = await executor.execute(
            metadata,
            instructions="Consider algorithm A with O(n²) complexity.",
            output_format="Acknowledge",
            context=[],
            session_id=session_id,
            reasoning_effort="high",
        )

        data1 = json.loads(result1)
        # MockAdapter doesn't pass through reasoning_effort in adapter_kwargs
        # But we can verify it was accepted
        assert data1["turn_count"] == 1

        # Second turn: Follow-up question
        result2 = await executor.execute(
            metadata,
            instructions="How can we optimize algorithm A?",
            output_format="Provide optimization strategies",
            context=[],
            session_id=session_id,
        )

        data2 = json.loads(result2)
        # Should have context about algorithm A
        assert "algorithm A" in data2["prompt"] or "O(n²)" in data2["prompt"]
        # Note: With MockAdapter, we verify plumbing instead of tool usage

    @pytest.mark.asyncio
    async def test_gpt4_multi_turn(self, clean_session_caches, session_id_generator):
        """Test GPT-4.1 multi-turn conversations."""
        metadata = get_tool("chat_with_gpt41")
        session_id = session_id_generator()

        # Turn 1
        await executor.execute(
            metadata,
            instructions="The project name is Skynet.",
            output_format="OK",
            context=[],
            session_id=session_id,
        )

        # Turn 2
        result = await executor.execute(
            metadata,
            instructions="What's the project name?",
            output_format="Answer",
            context=[],
            session_id=session_id,
        )

        data = json.loads(result)
        assert "Skynet" in data["prompt"]
        # Note: With MockAdapter, we verify plumbing instead of tool usage

    @pytest.mark.asyncio
    async def test_openai_system_prompt_priority(
        self, clean_session_caches, session_id_generator
    ):
        """Test that OpenAI models get the updated priority instructions."""
        metadata = get_tool("chat_with_gpt52_pro")
        session_id = session_id_generator()

        result = await executor.execute(
            metadata,
            instructions="Test",
            output_format="Test",
            context=[],
            session_id=session_id,
        )

        data = json.loads(result)
        messages = data["adapter_kwargs"]["messages"]

        # Find developer message
        dev_msg = next((m for m in messages if m["role"] == "developer"), None)
        assert dev_msg is not None

        # Verify priority instructions
        assert "Information priority:" in dev_msg["content"]
        assert "Current conversation" in dev_msg["content"]
        assert (
            "search_project_history - for historical project information"
            in dev_msg["content"]
        )

    @pytest.mark.asyncio
    async def test_research_models_multi_turn(
        self, clean_session_caches, session_id_generator
    ):
        """Test research models (o3-deep-research) maintain context."""
        metadata = get_tool("research_with_o3_deep_research")
        session_id = session_id_generator()

        # Note: Research models have long response times, mock adapter handles this
        result1 = await executor.execute(
            metadata,
            instructions="Research topic: Quantum computing applications",
            output_format="Brief overview",
            context=[],
            session_id=session_id,
        )

        data1 = json.loads(result1)
        assert data1["adapter_kwargs"]["session_id"] == session_id

        # Follow-up
        result2 = await executor.execute(
            metadata,
            instructions="Focus on the medical applications mentioned",
            output_format="Detailed analysis",
            context=[],
            session_id=session_id,
        )

        data2 = json.loads(result2)
        # Should have previous context
        assert "Quantum computing" in data2["prompt"]
        # Note: With MockAdapter, we verify plumbing instead of tool usage
