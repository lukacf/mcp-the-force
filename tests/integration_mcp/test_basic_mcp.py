"""Basic MCP integration tests - just verify tools can be called."""

import pytest
from mcp.types import TextContent
import json
import uuid

# Use anyio for better async handling - but only with asyncio backend
# This prevents "ModuleNotFoundError: No module named 'trio'" errors
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.parametrize("anyio_backend", ["asyncio"], indirect=True),
]


class TestBasicMCP:
    """Simple tests that MCP protocol works."""

    async def test_list_sessions_callable(self, mcp_server):
        """Test that list_sessions can be called and returns expected type."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        # Create client within test to avoid async teardown issues
        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            # Call the tool with parameters (MCP expects string values)
            result = await client.call_tool("list_sessions", arguments={"limit": "5"})

            # Check if the tool call was successful
            assert not result.is_error, f"Tool call failed with error: {getattr(result, 'error_message', 'Unknown error')}"

            # Access the actual response from the .content attribute
            content = result.content
            assert isinstance(content, list)

            # The result is a list of TextContent items
            if len(content) > 0:
                first_item = content[0]
                assert isinstance(first_item, TextContent)

                # Parse the JSON array from the first TextContent
                sessions = json.loads(first_item.text)
                assert isinstance(sessions, list)

                # Each session should have required fields
                for session_data in sessions:
                    assert "session_id" in session_data
                    assert "tool_name" in session_data

    async def test_gemini_tool_callable(self, mcp_server):
        """Test that a model tool can be called."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool(
                "chat_with_gemini25_pro",
                {
                    "instructions": "test",
                    "output_format": "json",
                    "context": [],
                    "session_id": "mcp-gemini",
                },
            )

            # Check if the tool call was successful
            assert not result.is_error, f"Tool call failed with error: {getattr(result, 'error_message', 'Unknown error')}"

            # Access the actual response from the .content attribute
            content = result.content
            assert isinstance(content, list)
            assert len(content) == 1
            assert isinstance(content[0], TextContent)

            # Mock should return JSON (but handle if it doesn't)
            try:
                data = json.loads(content[0].text)
                assert data["model"] == "gemini-2.5-pro"
            except json.JSONDecodeError:
                # If not JSON, just verify we got a response
                assert len(content[0].text) > 0

    async def test_grok_tool_callable(self, mcp_server):
        """Test that a Grok tool can be called via MCP."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool(
                "chat_with_grok4",
                {
                    "instructions": "test",
                    "output_format": "json",
                    "context": [],
                    "session_id": f"mcp-grok-{uuid.uuid4()}",
                },
            )

            # Check if the tool call was successful
            assert not result.is_error, f"Tool call failed with error: {getattr(result, 'error_message', 'Unknown error')}"

            # Access the actual response from the .content attribute
            content = result.content
            assert isinstance(content, list) and len(content) == 1
            assert isinstance(content[0], TextContent)

            # MockAdapter returns JSON metadata
            data = json.loads(content[0].text)
            assert data["mock"] is True
            assert data["model"] == "grok-4"
            assert data["prompt_length"] > 0

    async def test_count_project_tokens_callable(self, mcp_server):
        """Test count_project_tokens tool."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            # Use the current directory (should be the project root during tests)
            result = await client.call_tool(
                "count_project_tokens", {"items": ["pyproject.toml"]}
            )

            # Check if the tool call was successful
            assert not result.is_error, f"Tool call failed with error: {getattr(result, 'error_message', 'Unknown error')}"

            # Access the actual response from the .content attribute
            content = result.content
            assert isinstance(content, list)
            assert len(content) == 1

            data = json.loads(content[0].text)
            assert "total_tokens" in data
            assert "total_files" in data
            assert "largest_files" in data
            assert "largest_directories" in data
            assert isinstance(data["total_tokens"], int)
            assert isinstance(data["total_files"], int)
            assert data["total_tokens"] > 0
            assert data["total_files"] == 1
            # Check that pyproject.toml is in the largest_files
            assert len(data["largest_files"]) == 1
            assert any("pyproject.toml" in f["path"] for f in data["largest_files"])

    async def test_search_project_history_callable(
        self, mcp_server, mock_env, mock_openai_factory
    ):
        """Test search_project_history tool via MCP."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool("search_project_history", {"query": "test"})

            # Check if the tool call was successful
            assert not result.is_error, f"Tool call failed with error: {getattr(result, 'error_message', 'Unknown error')}"

            # Access the actual response from the .content attribute
            content = result.content
            assert isinstance(content, list)
            assert len(content) == 1
            assert isinstance(content[0], TextContent)
