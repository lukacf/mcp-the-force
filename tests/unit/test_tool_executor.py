"""
Unit tests for ToolExecutor orchestration.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import fastmcp.exceptions
from mcp_the_force.tools.executor import ToolExecutor
from mcp_the_force.tools.registry import get_tool

# Import definitions to ensure tools are registered
from mcp_the_force.tools import definitions  # noqa: F401
from mcp_the_force.adapters.base import BaseAdapter


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
        from mcp_the_force.adapters import _ADAPTER_CACHE

        _ADAPTER_CACHE.clear()

        # Mock the adapter creation
        with patch("mcp_the_force.adapters.get_adapter") as mock_get_adapter:
            mock_get_adapter.return_value = (mock_adapter, None)

            # Also ensure the vertex client is mocked
            with patch(
                "mcp_the_force.adapters.vertex.adapter.get_client"
            ) as mock_get_client:
                mock_get_client.return_value = (
                    Mock()
                )  # Won't be used since we mock get_adapter

                metadata = get_tool("chat_with_gemini25_flash")
                result = await executor.execute(
                    metadata,
                    instructions="Explain this code",
                    output_format="markdown",
                    context=[str(test_file)],
                    temperature=0.5,
                    session_id="gemini-test",
                )

                # Check that our mock was used
                assert mock_get_adapter.called

        # Verify adapter was called with correct params
        assert mock_adapter.generate.call_count >= 1
        call_args = mock_adapter.generate.call_args_list[0]

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
        with patch("mcp_the_force.adapters.get_adapter") as mock_get_adapter:
            mock_get_adapter.return_value = (mock_adapter, None)

            # Mock session cache
            from unittest.mock import AsyncMock

            with patch("mcp_the_force.session_cache.session_cache") as mock_cache:
                mock_cache.get_response_id = AsyncMock(
                    return_value="previous_response_id"
                )
                mock_cache.set_response_id = AsyncMock()

                metadata = get_tool("chat_with_o3")
                await executor.execute(
                    metadata,
                    instructions="Continue our discussion",
                    output_format="text",
                    context=[],
                    session_id="test-session",
                    reasoning_effort="high",
                )

        # Verify session was used
        mock_cache.get_response_id.assert_called_with("test-session")

        # Verify adapter was called
        assert mock_adapter.generate.called

    @pytest.mark.asyncio
    async def test_missing_required_parameter(self, executor):
        """Test that missing required parameter raises appropriate error."""
        with pytest.raises(fastmcp.exceptions.ToolError, match="Tool execution failed"):
            metadata = get_tool("chat_with_gemini25_flash")
            await executor.execute(
                metadata,
                instructions="Test",
                # Missing output_format and context
                session_id="missing-param",
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
        with patch("mcp_the_force.adapters.get_adapter") as mock_get_adapter:
            # Simulate adapter creation failure
            mock_get_adapter.return_value = (
                None,
                "Failed to create adapter: Invalid API key",
            )

            metadata = get_tool("chat_with_gemini25_flash")
            with pytest.raises(fastmcp.exceptions.ToolError):
                await executor.execute(
                    metadata,
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="adapter-error",
                )
