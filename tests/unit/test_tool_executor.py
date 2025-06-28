"""
Unit tests for ToolExecutor orchestration.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from mcp_second_brain.tools.executor import ToolExecutor
from mcp_second_brain.tools.registry import get_tool

# Import definitions to ensure tools are registered
from mcp_second_brain.tools import definitions  # noqa: F401
from mcp_second_brain.adapters.base import BaseAdapter


class TestToolExecutor:
    """Test the ToolExecutor orchestration."""

    @pytest.fixture
    def executor(self):
        """Create a ToolExecutor instance."""
        return ToolExecutor()

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter."""
        adapter = Mock(spec=BaseAdapter)
        adapter.generate = AsyncMock(return_value="Mock response")
        return adapter

    @pytest.mark.asyncio
    async def test_execute_gemini_tool(
        self, executor, mock_adapter, tmp_path, mock_env
    ):
        """Test executing a Gemini tool with proper parameter routing."""
        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # Clear adapter cache first
        from mcp_second_brain.adapters import _ADAPTER_CACHE

        _ADAPTER_CACHE.clear()

        # Mock the adapter creation
        with patch("mcp_second_brain.adapters.get_adapter") as mock_get_adapter:
            mock_get_adapter.return_value = (mock_adapter, None)

            # Also ensure the vertex client is mocked
            with patch(
                "mcp_second_brain.adapters.vertex.adapter.get_client"
            ) as mock_get_client:
                mock_get_client.return_value = (
                    Mock()
                )  # Won't be used since we mock get_adapter

                metadata = get_tool("chat_with_gemini25_flash")
                result = await executor.execute(
                    metadata,
                    instructions="Explain this code",
                    output_format="markdown",
                    context_paths=[str(test_file)],
                    temperature=0.5,
                )

                # Check that our mock was used
                mock_get_adapter.assert_called_once()

        # Verify adapter was called with correct params
        mock_adapter.generate.assert_called_once()
        call_args = mock_adapter.generate.call_args

        # Check prompt was built
        prompt = call_args[1]["prompt"]
        assert "Explain this code" in prompt
        assert "markdown" in prompt
        assert "print('hello')" in prompt  # File content should be inlined

        # Check adapter params
        assert call_args[1].get("temperature") == 0.5

        # Check result
        assert result == "Mock response"

    @pytest.mark.asyncio
    async def test_execute_openai_tool_with_session(self, executor, mock_adapter):
        """Test executing an OpenAI tool with session support."""
        with patch("mcp_second_brain.adapters.get_adapter") as mock_get_adapter:
            mock_get_adapter.return_value = (mock_adapter, None)

            # Mock session cache
            with patch("mcp_second_brain.session_cache.session_cache") as mock_cache:
                mock_cache.get_response_id.return_value = "previous_response_id"

                metadata = get_tool("chat_with_o3")
                await executor.execute(
                    metadata,
                    instructions="Continue our discussion",
                    output_format="text",
                    context_paths=[],
                    session_id="test-session",
                    reasoning_effort="high",
                )

        # Verify session was used
        mock_cache.get_response_id.assert_called_with("test-session")

        # Verify adapter was called
        assert mock_adapter.generate.called

    @pytest.mark.asyncio
    async def test_vector_store_routing(self, executor, mock_adapter, tmp_path):
        """Test that attachments parameter triggers vector store creation."""
        # Create a file for attachment
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        # Mock session cache to avoid database access
        with patch(
            "mcp_second_brain.session_cache.session_cache"
        ) as mock_session_cache:
            mock_session_cache.get_response_id.return_value = None
            mock_session_cache.set_response_id.return_value = None

            with patch("mcp_second_brain.adapters.get_adapter") as mock_get_adapter:
                mock_get_adapter.return_value = (mock_adapter, None)

                # Patch the vector store manager instance in the executor
                with patch.object(
                    executor.vector_store_manager, "create", new_callable=AsyncMock
                ) as mock_create:
                    mock_create.return_value = "vs_123"

                    metadata = get_tool("chat_with_gpt4_1")
                    await executor.execute(
                        metadata,
                        instructions="Analyze this",
                        output_format="text",
                        context_paths=[],
                        attachment_paths=[str(tmp_path)],  # Pass directory
                        session_id="test",
                    )

        # Verify vector store was created
        mock_create.assert_called_once()
        # The create method receives gathered file paths
        call_args = mock_create.call_args[0][0]
        assert any("test.txt" in f for f in call_args)

    @pytest.mark.asyncio
    async def test_missing_required_parameter(self, executor):
        """Test that missing required parameter raises appropriate error."""
        with pytest.raises(ValueError, match="Missing required parameter"):
            metadata = get_tool("chat_with_gemini25_flash")
            await executor.execute(
                metadata,
                instructions="Test",
                # Missing output_format and context
            )

    @pytest.mark.asyncio
    async def test_invalid_tool_name(self, executor):
        """Test that invalid tool name returns None."""
        # Test that get_tool returns None for invalid tools
        metadata = get_tool("invalid_tool_name")
        assert metadata is None

        # Can't execute with None metadata
        if metadata is None:
            # This is the expected behavior
            pass

    @pytest.mark.asyncio
    async def test_adapter_error_handling(self, executor):
        """Test that adapter errors are handled gracefully."""
        with patch("mcp_second_brain.adapters.get_adapter") as mock_get_adapter:
            # Simulate adapter creation failure
            mock_get_adapter.return_value = (
                None,
                "Failed to create adapter: Invalid API key",
            )

            # The executor returns error message instead of raising
            metadata = get_tool("chat_with_gemini25_flash")
            result = await executor.execute(
                metadata, instructions="Test", output_format="text", context_paths=[]
            )
            assert "Error: Failed to initialize adapter" in result
