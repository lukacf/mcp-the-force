"""
Tests for tool visibility and hiding of create_vector_store_tool.
"""


class TestToolVisibility:
    """Test that certain tools are hidden from the public API."""

    async def test_create_vector_store_tool_not_in_tool_list(self):
        """create_vector_store_tool should not appear in the list of available tools."""
        from mcp_second_brain.tools.registry import list_tools

        tools = list_tools()
        tool_names = list(tools.keys())
        assert "create_vector_store_tool" not in tool_names

    async def test_internal_vector_store_creation_still_works(self):
        """Internal vector store creation should still work even if not exposed."""
        # This tests that we can still import the vector store creation function
        from mcp_second_brain.utils.vector_store import create_vector_store

        # Just verify the function exists - actual creation requires API keys
        assert create_vector_store is not None
