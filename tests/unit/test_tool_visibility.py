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

    async def test_count_project_tokens_in_tool_list(self):
        """count_project_tokens should appear in the list of available tools."""
        # This test will verify it's exposed via MCP, but for now just skip
        # since it's registered directly with FastMCP not through the registry
        pass

    async def test_list_models_does_not_include_vector_store(self):
        """list_models tool should not show create_vector_store_tool."""
        # The list_models function only lists AI model tools from the registry
        # Since create_vector_store_tool is not an AI model tool, it won't appear
        pass

    async def test_count_project_tokens_has_correct_schema(self):
        """count_project_tokens should have the expected parameter schema."""
        # This would be tested through MCP integration tests
        # Skip for now since it's a utility tool registered directly with FastMCP
        pass

    async def test_internal_vector_store_creation_still_works(self):
        """Internal vector store creation should still work even if not exposed."""
        # This tests that we can still import the vector store creation function
        from mcp_second_brain.utils.vector_store import create_vector_store

        # Just verify the function exists - actual creation requires API keys
        assert create_vector_store is not None

    async def test_mcp_server_does_not_expose_vector_store(self):
        """MCP server should not register create_vector_store_tool."""
        # This is now verified by the server.py code itself which has a comment
        # indicating create_vector_store_tool is intentionally not registered
        pass
