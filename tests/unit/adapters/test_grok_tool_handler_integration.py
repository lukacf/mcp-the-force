"""
Tests for Grok adapter integration with ToolHandler.

This test specifically validates that the bug fix for attachment handling
works correctly by ensuring the search_session_attachments tool is
properly declared when vector_store_ids are provided.
"""

import pytest
from unittest.mock import patch, MagicMock
from mcp_second_brain.adapters.grok.adapter import GrokAdapter
from mcp_second_brain.adapters.tool_handler import ToolHandler


class TestGrokToolHandlerIntegration:
    """Test that Grok adapter properly integrates with ToolHandler."""

    @pytest.fixture
    def mock_grok_settings(self):
        """Mock the settings to provide a fake API key."""
        with patch(
            "mcp_second_brain.adapters.grok.adapter.get_settings"
        ) as mock_settings:
            mock_config = MagicMock()
            mock_config.xai.api_key = "fake-api-key"
            mock_settings.return_value = mock_config
            yield mock_config

    def test_tool_handler_initialization(self, mock_grok_settings):
        """Test that GrokAdapter properly initializes ToolHandler."""
        adapter = GrokAdapter("grok-4")
        assert hasattr(adapter, "tool_handler")
        assert isinstance(adapter.tool_handler, ToolHandler)

    def test_tool_declarations_without_vector_stores(self, mock_grok_settings):
        """Test tool declarations when no vector stores are provided."""
        adapter = GrokAdapter("grok-4")

        # Should only declare search_project_memory
        tools = adapter.tool_handler.prepare_tool_declarations(
            adapter_type="grok", vector_store_ids=None
        )

        assert len(tools) == 1
        # Check the actual structure - OpenAI tool format
        tool = tools[0]
        assert tool["type"] == "function"
        assert tool["name"] == "search_project_memory"
        assert "description" in tool
        assert "parameters" in tool

    def test_tool_declarations_with_vector_stores(self, mock_grok_settings):
        """Test tool declarations when vector stores are provided - this is the bug fix."""
        adapter = GrokAdapter("grok-4")

        # Should declare both search_project_memory and search_session_attachments
        tools = adapter.tool_handler.prepare_tool_declarations(
            adapter_type="grok", vector_store_ids=["vs-123", "vs-456"]
        )

        assert len(tools) == 2

        # Check first tool (search_project_memory)
        memory_tool = tools[0]
        assert memory_tool["type"] == "function"
        assert memory_tool["name"] == "search_project_memory"
        assert "description" in memory_tool
        assert "parameters" in memory_tool

        # Check second tool (search_session_attachments) - this was missing before the fix
        attachment_tool = tools[1]
        assert attachment_tool["type"] == "function"
        assert attachment_tool["name"] == "search_session_attachments"
        assert "description" in attachment_tool
        assert "parameters" in attachment_tool

    def test_tool_execution_search_project_memory(self, mock_grok_settings):
        """Test that tool execution works for search_project_memory."""
        adapter = GrokAdapter("grok-4")

        # Mock the SearchMemoryAdapter
        with patch(
            "mcp_second_brain.tools.search_memory.SearchMemoryAdapter"
        ) as mock_adapter:
            mock_instance = mock_adapter.return_value

            # Make the mock return a coroutine
            async def mock_generate(**kwargs):
                return "memory search result"

            mock_instance.generate = mock_generate

            # Execute the tool
            result = adapter.tool_handler.execute_tool_call(
                tool_name="search_project_memory",
                tool_args={"query": "test query"},
                vector_store_ids=None,
            )

            # Should be wrapped in a coroutine, so we need to await it
            import asyncio

            result = asyncio.run(result)

            assert result == "memory search result"

    def test_tool_execution_search_session_attachments(self, mock_grok_settings):
        """Test that tool execution works for search_session_attachments."""
        adapter = GrokAdapter("grok-4")
        vector_store_ids = ["vs-123"]

        # Mock the SearchAttachmentAdapter
        with patch(
            "mcp_second_brain.tools.search_attachments.SearchAttachmentAdapter"
        ) as mock_adapter:
            mock_instance = mock_adapter.return_value

            # Make the mock return a coroutine
            async def mock_generate(**kwargs):
                return "attachment search result"

            mock_instance.generate = mock_generate

            # Execute the tool
            result = adapter.tool_handler.execute_tool_call(
                tool_name="search_session_attachments",
                tool_args={"query": "test query"},
                vector_store_ids=vector_store_ids,
            )

            # Should be wrapped in a coroutine, so we need to await it
            import asyncio

            result = asyncio.run(result)

            assert result == "attachment search result"

    def test_unknown_tool_execution(self, mock_grok_settings):
        """Test handling of unknown tools."""
        adapter = GrokAdapter("grok-4")

        # Execute unknown tool
        result = adapter.tool_handler.execute_tool_call(
            tool_name="unknown_tool", tool_args={"query": "test"}, vector_store_ids=None
        )

        # Should be wrapped in a coroutine, so we need to await it
        import asyncio

        result = asyncio.run(result)

        assert "Error: Unknown tool 'unknown_tool'" in result

    def test_tool_execution_error_handling(self, mock_grok_settings):
        """Test that tool execution errors are properly handled."""
        adapter = GrokAdapter("grok-4")

        # Mock the SearchMemoryAdapter to raise an exception
        with patch(
            "mcp_second_brain.tools.search_memory.SearchMemoryAdapter"
        ) as mock_adapter:
            mock_instance = mock_adapter.return_value

            # Make the mock raise an exception in an async context
            async def mock_generate(**kwargs):
                raise Exception("Test error")

            mock_instance.generate = mock_generate

            # Execute the tool - should raise the exception
            with pytest.raises(Exception, match="Test error"):
                result = adapter.tool_handler.execute_tool_call(
                    tool_name="search_project_memory",
                    tool_args={"query": "test query"},
                    vector_store_ids=None,
                )

                # Should be wrapped in a coroutine, so we need to await it
                import asyncio

                asyncio.run(result)
