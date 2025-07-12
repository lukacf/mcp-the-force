"""
Integration test for vector store retrieval functionality.
"""

import pytest
from unittest.mock import Mock
from mcp_second_brain.tools.executor import executor
from mcp_second_brain.tools.registry import get_tool

# Import definitions to ensure tools are registered
import mcp_second_brain.tools.definitions  # noqa: F401


class TestVectorStoreRetrieval:
    """Test that vector stores can be created AND used for retrieval."""

    @pytest.mark.asyncio
    async def test_vector_store_create_and_retrieve(self, tmp_path, mock_openai_client):
        """Test creating a vector store and then using it to answer questions."""
        # Create specialized content that won't be in the model's training
        secret_file = tmp_path / "secret_process.md"
        secret_file.write_text("""
# Secret Process Documentation

The ZEPHYR process consists of exactly 7 steps:
1. Initialize the quantum stabilizer
2. Calibrate the flux capacitor to 1.21 gigawatts
3. Engage the temporal synchronizer
4. Activate the ZEPHYR core
5. Monitor the chronoton levels
6. Adjust the tachyon flow
7. Complete the ZEPHYR sequence

Important: The ZEPHYR code is: QX-7742-ALPHA
""")

        another_file = tmp_path / "unrelated.txt"
        another_file.write_text(
            "This file contains unrelated information about cooking recipes."
        )

        # Mock vector store creation
        mock_openai_client.vector_stores.create.return_value = Mock(
            id="vs_retrieval_test", status="completed"
        )

        # Mock file upload
        mock_openai_client.vector_stores.file_batches.upload_and_poll.return_value = (
            Mock(status="completed", file_counts=Mock(completed=2, failed=0))
        )

        # First: Ingest the documents
        tool_metadata = get_tool("chat_with_gpt4_1")
        if not tool_metadata:
            raise ValueError("Tool chat_with_gpt4_1 not found")
        result1 = await executor.execute(
            tool_metadata,
            instructions="Store these documents for later retrieval",
            output_format="confirmation",
            context=[],  # Empty inline context
            attachments=[str(tmp_path)],  # Use vector store
            session_id="retrieval-test",
        )

        # Parse MockAdapter response
        import json

        data1 = json.loads(result1)
        assert data1["mock"] is True
        # Note: May include auto-attached memory stores
        assert "vs_retrieval_test" in data1["vector_store_ids"]

        # Verify vector store was created
        mock_openai_client.vector_stores.create.assert_called_once()

        # Second: Ask a specific question that requires retrieval
        # Note: Current implementation doesn't persist vector stores across calls
        # Each call needs its own attachments to use vector store
        result2 = await executor.execute(
            tool_metadata,
            instructions="What is the ZEPHYR code and how many gigawatts are needed?",
            output_format="specific answer only",
            context=[],  # Empty inline context
            attachments=[str(tmp_path)],  # Need to provide attachments again
            session_id="retrieval-test",  # Same session
        )

        # Parse second response
        data2 = json.loads(result2)
        assert data2["mock"] is True
        assert "ZEPHYR code" in data2["prompt"]
        assert data2["vector_store_ids"] is not None

        # Verify both calls created vector stores
        assert mock_openai_client.vector_stores.create.call_count == 2

    @pytest.mark.asyncio
    async def test_vector_store_cross_session_retrieval(
        self, tmp_path, mock_openai_client
    ):
        """Test that vector stores can be used across different sessions."""
        # Create unique content
        (tmp_path / "protocol.txt").write_text("""
The OMEGA protocol activation sequence:
- Code: OMEGA-2024-SECURE
- Frequency: 742.5 MHz
- Duration: 45 seconds
""")

        # Mock vector store
        mock_openai_client.vector_stores.create.return_value = Mock(id="vs_shared")
        mock_openai_client.vector_stores.file_batches.upload_and_poll.return_value = (
            Mock(status="completed")
        )

        # Create vector store in one session
        tool_metadata = get_tool("chat_with_gpt4_1")
        if not tool_metadata:
            raise ValueError("Tool chat_with_gpt4_1 not found")
        result1 = await executor.execute(
            tool_metadata,
            instructions="Store this protocol information",
            output_format="brief",
            context=[],
            attachments=[str(tmp_path)],
            session_id="session-1",
        )

        # Parse first response
        import json

        data1 = json.loads(result1)
        assert data1["mock"] is True
        # Note: May include auto-attached memory stores
        assert "vs_shared" in data1["vector_store_ids"]

        # Use it in a different session (simulating another user/context)
        # Note: Current implementation requires providing attachments again
        result2 = await executor.execute(
            tool_metadata,
            instructions="What is the OMEGA code and frequency?",
            output_format="specific values only",
            context=[],
            attachments=[str(tmp_path)],  # Need to provide attachments
            session_id="session-2",  # Different session
        )

        # Parse second response
        data2 = json.loads(result2)
        assert data2["mock"] is True
        assert "OMEGA code" in data2["prompt"]
        assert data2["vector_store_ids"] is not None

    @pytest.mark.asyncio
    async def test_vector_store_with_no_relevant_content(
        self, tmp_path, mock_openai_client
    ):
        """Test vector store behavior when query has no relevant content."""
        # Create files with irrelevant content
        (tmp_path / "recipes.txt").write_text("How to make chocolate cake...")
        (tmp_path / "weather.txt").write_text("Today's weather forecast...")

        # Mock vector store creation
        mock_openai_client.vector_stores.create.return_value = Mock(id="vs_irrelevant")
        mock_openai_client.vector_stores.file_batches.upload_and_poll.return_value = (
            Mock(status="completed")
        )

        tool_metadata = get_tool("chat_with_gpt4_1")
        if not tool_metadata:
            raise ValueError("Tool chat_with_gpt4_1 not found")
        result = await executor.execute(
            tool_metadata,
            instructions="Explain quantum entanglement",
            output_format="detailed explanation",
            context=[],
            attachments=[str(tmp_path)],
            session_id="test-irrelevant",
        )

        # Parse MockAdapter response
        import json

        data = json.loads(result)
        assert data["mock"] is True
        # Note: May include auto-attached memory stores
        assert "vs_irrelevant" in data["vector_store_ids"]
        assert "quantum entanglement" in data["prompt"]
