"""Basic MCP integration tests - just verify tools can be called."""
import pytest
from mcp.types import TextContent
import json

# Use anyio for better async handling - but only with asyncio backend  
# This prevents "ModuleNotFoundError: No module named 'trio'" errors
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.parametrize("anyio_backend", ["asyncio"], indirect=True)
]


class TestBasicMCP:
    """Simple tests that MCP protocol works."""
    
    async def test_list_models_callable(self, mcp_server):
        """Test that list_models can be called and returns expected type."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport
        
        # Create client within test to avoid async teardown issues
        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            # Call the tool
            result = await client.call_tool("list_models")
            
            # list_models returns a list of TextContent objects
            assert isinstance(result, list)
            assert len(result) > 0
            
            # Each item should be parseable as JSON
            for item in result:
                assert isinstance(item, TextContent)
                model_data = json.loads(item.text)
                assert "id" in model_data
                assert "model" in model_data
    
    async def test_gemini_tool_callable(self, mcp_server):
        """Test that a model tool can be called."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport
        
        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool("chat_with_gemini25_pro", {
                "instructions": "test",
                "output_format": "json", 
                "context": []
            })
            
            # Tools return lists of TextContent
            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            
            # Mock should return JSON (but handle if it doesn't)
            try:
                data = json.loads(result[0].text)
                assert data["model"] == "gemini-2.5-pro"
            except json.JSONDecodeError:
                # If not JSON, just verify we got a response
                assert len(result[0].text) > 0
    
    async def test_vector_store_callable(self, mcp_server):
        """Test vector store tool."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport
        
        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool("create_vector_store_tool", {
                "files": ["/tmp/test.txt"]
            })
            
            # This tool also returns a list
            assert isinstance(result, list)
            assert len(result) == 1
            
            data = json.loads(result[0].text)
            assert "vector_store_id" in data

    async def test_search_project_memory_callable(self, mcp_server):
        """Test search_project_memory tool via MCP."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool("search_project_memory", {"query": "test"})

            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], TextContent)

    async def test_search_session_attachments_callable(self, mcp_server, tmp_path):
        """Test search_session_attachments tool via MCP."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        test_file = tmp_path / "sample.txt"
        test_file.write_text("hello world")

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            vs_result = await client.call_tool(
                "create_vector_store_tool", {"files": [str(test_file)]}
            )

            vs_data = json.loads(vs_result[0].text)
            vs_id = vs_data.get("vector_store_id")

            result = await client.call_tool(
                "search_session_attachments",
                {"query": "hello", "vector_store_ids": [vs_id]},
            )

            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
