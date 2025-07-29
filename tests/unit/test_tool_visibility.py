"""
Tests for tool visibility and hiding of create_vector_store_tool.
"""


class TestToolVisibility:
    """Test that certain tools are hidden from the public API."""

    async def test_create_vector_store_tool_not_in_tool_list(self):
        """create_vector_store_tool should not appear in the list of available tools."""
        from mcp_the_force.tools.registry import list_tools

        tools = list_tools()
        tool_names = list(tools.keys())
        assert "create_vector_store_tool" not in tool_names

    async def test_internal_vector_store_creation_still_works(self):
        """Internal vector store creation should still work even if not exposed."""
        # This tests that we can still import the vector store manager
        from mcp_the_force.vectorstores.manager import vector_store_manager

        # Just verify the manager exists and has the create method
        assert vector_store_manager is not None
        assert hasattr(vector_store_manager, "create")
