"""Integration tests for Gemini parameter routing and prompt construction.

These tests verify the internal mechanics of session management using MockAdapter.
They focus on testing that parameters are correctly routed and prompts are properly
constructed. They do NOT test actual model behavior.
"""

import pytest
import json
from mcp_second_brain.tools.executor import executor
from mcp_second_brain.tools.registry import get_tool
from unittest.mock import patch


class TestGeminiMechanics:
    """Test parameter routing and prompt construction for Gemini models."""

    @pytest.mark.asyncio
    async def test_session_id_routing(self, clean_session_caches, session_id_generator):
        """Test that session_id is correctly passed to the adapter."""
        metadata = get_tool("chat_with_gemini25_pro")
        session_id = session_id_generator()

        result = await executor.execute(
            metadata,
            instructions="Test prompt",
            output_format="text",
            context=[],
            session_id=session_id,
        )

        data = json.loads(result)  # MockAdapter returns JSON metadata

        # Verify session_id was passed to adapter (would catch Bug #1)
        assert "session_id" in data["adapter_kwargs"]
        assert data["adapter_kwargs"]["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_system_instruction_on_all_turns(
        self, clean_session_caches, session_id_generator
    ):
        """Test that system_instruction is sent on every turn, not just first."""
        metadata = get_tool("chat_with_gemini25_pro")
        session_id = session_id_generator()

        # First turn
        result1 = await executor.execute(
            metadata,
            instructions="First message",
            output_format="OK",
            context=[],
            session_id=session_id,
        )

        data1 = json.loads(result1)
        assert "system_instruction" in data1["adapter_kwargs"]

        # Second turn - this is where Bug #2 occurred
        result2 = await executor.execute(
            metadata,
            instructions="Second message",
            output_format="OK",
            context=[],
            session_id=session_id,
        )

        data2 = json.loads(result2)
        # Bug #2: system_instruction must be sent on ALL turns
        assert "system_instruction" in data2["adapter_kwargs"]
        assert data2["adapter_kwargs"]["system_instruction"] is not None

    @pytest.mark.asyncio
    async def test_conversation_history_handled_by_adapter(
        self, clean_session_caches, session_id_generator
    ):
        """Test that session_id enables history handling in the adapter.

        Note: With MockAdapter, we can't see the full conversation history
        because the Vertex adapter loads it internally. We can only verify
        that the session_id is passed, enabling the adapter to load history.
        """
        metadata = get_tool("chat_with_gemini25_pro")
        session_id = session_id_generator()

        # First turn
        result1 = await executor.execute(
            metadata,
            instructions="My unique identifier is ABC123",
            output_format="OK",
            context=[],
            session_id=session_id,
        )

        data1 = json.loads(result1)
        assert data1["adapter_kwargs"]["session_id"] == session_id

        # Second turn
        result2 = await executor.execute(
            metadata,
            instructions="What is my identifier?",
            output_format="Tell me",
            context=[],
            session_id=session_id,
        )

        data2 = json.loads(result2)

        # We can verify:
        # 1. Session ID is still passed (enables history loading)
        assert data2["adapter_kwargs"]["session_id"] == session_id

        # 2. Current message is in the prompt
        assert "What is my identifier?" in data2["prompt"]

        # Note: We CANNOT verify the conversation history is included
        # because the Vertex adapter loads it internally when it sees
        # the session_id. This would require an e2e test.

    @pytest.mark.asyncio
    async def test_priority_instructions_included(
        self, clean_session_caches, session_id_generator
    ):
        """Test that updated priority instructions are in system_instruction."""
        metadata = get_tool("chat_with_gemini25_pro")
        session_id = session_id_generator()

        result = await executor.execute(
            metadata,
            instructions="Test",
            output_format="Test",
            context=[],
            session_id=session_id,
        )

        data = json.loads(result)
        system_instruction = data["adapter_kwargs"]["system_instruction"]

        # Verify priority instructions that guide model behavior
        assert "Information priority order:" in system_instruction
        assert (
            "FIRST: Always check the current conversation history" in system_instruction
        )
        assert (
            "LAST: Use search_project_history only when you need historical information"
            in system_instruction
        )

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)  # Increase timeout for multiple executions
    async def test_session_isolation(self, clean_session_caches, session_id_generator):
        """Test that different sessions maintain separate histories."""
        metadata = get_tool("chat_with_gemini25_pro")
        session1 = session_id_generator()
        session2 = session_id_generator()

        # Session 1: Store fact A
        await executor.execute(
            metadata,
            instructions="Session 1 fact: FACT_A",
            output_format="OK",
            context=[],
            session_id=session1,
        )

        # Session 2: Store fact B
        await executor.execute(
            metadata,
            instructions="Session 2 fact: FACT_B",
            output_format="OK",
            context=[],
            session_id=session2,
        )

        # Query session 1
        result1 = await executor.execute(
            metadata,
            instructions="What fact?",
            output_format="Tell me",
            context=[],
            session_id=session1,
        )

        data1 = json.loads(result1)
        # Verify session 1 is used
        assert data1["adapter_kwargs"]["session_id"] == session1

        # Query session 2
        result2 = await executor.execute(
            metadata,
            instructions="What fact?",
            output_format="Tell me",
            context=[],
            session_id=session2,
        )

        data2 = json.loads(result2)
        # Verify session 2 is used
        assert data2["adapter_kwargs"]["session_id"] == session2

        # Note: We can't verify the actual conversation content with MockAdapter
        # because history is loaded internally by the adapter. We can only verify
        # that different session IDs are properly routed to the adapter.

    @pytest.mark.asyncio
    async def test_regression_missing_session_id_merge(self, clean_session_caches):
        """Regression test: Simulate bug where session params aren't merged."""
        metadata = get_tool("chat_with_gemini25_pro")

        # Capture what reaches the adapter
        adapter_calls = []

        # Patch the executor to simulate the bug
        original_execute = executor.execute

        async def buggy_execute(metadata, **kwargs):
            # Use the real router
            from mcp_second_brain.tools.parameter_router import ParameterRouter

            router = ParameterRouter()
            routed = router.route(metadata, kwargs)

            # Simulate bug: don't merge session params
            adapter_params = routed["adapter"]
            # adapter_params.update(routed["session"])  # BUG: Missing!

            # Capture what would reach adapter
            adapter_calls.append(adapter_params)

            # Return mock response
            return json.dumps({"adapter_kwargs": adapter_params})

        with patch.object(executor, "execute", buggy_execute):
            await executor.execute(
                metadata,
                instructions="Test",
                output_format="Test",
                context=[],
                session_id="test-session",
            )

        # Verify the bug: session_id NOT in adapter params
        assert len(adapter_calls) == 1
        assert "session_id" not in adapter_calls[0]

        # Now test with the fix
        adapter_calls.clear()

        # Normal execution (without bug)
        result = await original_execute(
            metadata,
            instructions="Test",
            output_format="Test",
            context=[],
            session_id="test-session",
        )

        data = json.loads(result)
        # With fix: session_id IS in adapter params
        assert "session_id" in data["adapter_kwargs"]
        assert data["adapter_kwargs"]["session_id"] == "test-session"

    @pytest.mark.asyncio
    async def test_gemini_flash_mechanics(
        self, clean_session_caches, session_id_generator
    ):
        """Test mechanics work for Gemini Flash model too."""
        metadata = get_tool("chat_with_gemini25_flash")
        session_id = session_id_generator()

        result = await executor.execute(
            metadata,
            instructions="Flash test",
            output_format="OK",
            context=[],
            session_id=session_id,
        )

        data = json.loads(result)

        # All mechanics should work for Flash too
        assert data["adapter_kwargs"]["session_id"] == session_id
        assert "system_instruction" in data["adapter_kwargs"]
        assert (
            "Information priority order:"
            in data["adapter_kwargs"]["system_instruction"]
        )
