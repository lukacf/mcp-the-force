"""
End-to-end tests for MCP protocol communication.
"""
import os
import json
import pytest
import httpx
import asyncio
from pathlib import Path


@pytest.mark.e2e
class TestMCPProtocol:
    """Test MCP protocol communication with real server."""
    
    @pytest.fixture
    def server_url(self):
        """Get MCP server URL from environment."""
        return os.getenv("MCP_SERVER_URL", "http://localhost:8000")
    
    @pytest.fixture
    async def mcp_client(self, server_url):
        """Create an HTTP client for MCP communication."""
        async with httpx.AsyncClient(base_url=server_url, timeout=30.0) as client:
            yield client
    
    @pytest.mark.asyncio
    async def test_server_health(self, mcp_client):
        """Test that server is healthy and responding."""
        response = await mcp_client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "healthy"
        assert "version" in data
    
    @pytest.mark.asyncio
    async def test_list_tools(self, mcp_client):
        """Test listing available tools via MCP protocol."""
        # MCP list tools request
        request_data = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1
        }
        
        response = await mcp_client.post("/", json=request_data)
        assert response.status_code == 200
        
        result = response.json()
        assert result.get("jsonrpc") == "2.0"
        assert result.get("id") == 1
        
        tools = result.get("result", {}).get("tools", [])
        assert len(tools) > 0
        
        # Check for expected tools
        tool_names = [tool["name"] for tool in tools]
        assert "chat_with_gemini25_flash" in tool_names
        assert "chat_with_gemini25_pro" in tool_names
        assert "chat_with_o3" in tool_names
        assert "chat_with_gpt4_1" in tool_names
    
    @pytest.mark.asyncio
    async def test_tool_execution_gemini(self, mcp_client):
        """Test executing a Gemini tool via MCP protocol."""
        # Create a simple test file
        test_content = "def hello():\n    return 'Hello, MCP!'"
        
        request_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "chat_with_gemini25_flash",
                "arguments": {
                    "instructions": "What does this function return?",
                    "output_format": "brief answer",
                    "context": [],  # Empty context for this test
                    "_inline_content": {  # Special param for testing
                        "test.py": test_content
                    }
                }
            },
            "id": 2
        }
        
        response = await mcp_client.post("/", json=request_data)
        assert response.status_code == 200
        
        result = response.json()
        assert result.get("jsonrpc") == "2.0"
        assert result.get("id") == 2
        
        # Check response contains expected content
        response_text = result.get("result", {}).get("content", "")
        assert len(response_text) > 0
        # Should mention "Hello" or "MCP" in the response
        assert "hello" in response_text.lower() or "mcp" in response_text.upper()
    
    @pytest.mark.asyncio
    async def test_tool_execution_with_context(self, mcp_client, tmp_path):
        """Test tool execution with file context."""
        # Create test files
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        
        (project_dir / "main.py").write_text("""
def calculate_sum(a, b):
    return a + b

if __name__ == "__main__":
    result = calculate_sum(5, 3)
    print(f"Result: {result}")
""")
        
        request_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "chat_with_gemini25_flash",
                "arguments": {
                    "instructions": "What does this code calculate?",
                    "output_format": "one sentence",
                    "context": [str(project_dir)]
                }
            },
            "id": 3
        }
        
        response = await mcp_client.post("/", json=request_data)
        assert response.status_code == 200
        
        result = response.json()
        response_text = result.get("result", {}).get("content", "")
        
        # Should understand it's calculating a sum
        assert "sum" in response_text.lower() or "add" in response_text.lower()
    
    @pytest.mark.asyncio
    async def test_error_handling(self, mcp_client):
        """Test MCP error handling."""
        # Test with missing required parameters
        request_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "chat_with_gemini25_flash",
                "arguments": {
                    "instructions": "Test"
                    # Missing required parameters
                }
            },
            "id": 4
        }
        
        response = await mcp_client.post("/", json=request_data)
        assert response.status_code == 200  # MCP errors are in response body
        
        result = response.json()
        assert "error" in result
        error = result["error"]
        assert error["code"] < 0  # Negative error codes for MCP
        assert "required parameter" in error["message"].lower()
    
    @pytest.mark.asyncio
    async def test_create_vector_store_tool(self, mcp_client, tmp_path):
        """Test vector store creation tool."""
        # Create test files
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "api.md").write_text("# API Documentation\n\nAPI endpoints...")
        (docs_dir / "guide.md").write_text("# User Guide\n\nHow to use...")
        
        request_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "create_vector_store_tool",
                "arguments": {
                    "files": [str(docs_dir)],
                    "name": "test-docs"
                }
            },
            "id": 5
        }
        
        response = await mcp_client.post("/", json=request_data)
        result = response.json()
        
        if "error" not in result:
            # If successful, should return vector store info
            vs_result = result.get("result", {}).get("content", {})
            if isinstance(vs_result, str):
                vs_result = json.loads(vs_result)
            
            assert "vector_store_id" in vs_result or "status" in vs_result
    
    @pytest.mark.asyncio
    async def test_list_models_tool(self, mcp_client):
        """Test list models tool."""
        request_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "list_models",
                "arguments": {}
            },
            "id": 6
        }
        
        response = await mcp_client.post("/", json=request_data)
        result = response.json()
        
        assert "error" not in result
        models_text = result.get("result", {}).get("content", "")
        
        # Should list available models
        assert "gemini" in models_text.lower()
        assert "o3" in models_text.lower()
        assert "gpt" in models_text.lower()
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_concurrent_requests(self, mcp_client):
        """Test handling concurrent MCP requests."""
        # Create multiple requests
        requests = []
        for i in range(5):
            request_data = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "chat_with_gemini25_flash",
                    "arguments": {
                        "instructions": f"Count to {i+1}",
                        "output_format": "numbers only",
                        "context": []
                    }
                },
                "id": 100 + i
            }
            requests.append(mcp_client.post("/", json=request_data))
        
        # Send all requests concurrently
        responses = await asyncio.gather(*requests)
        
        # All should succeed
        assert len(responses) == 5
        for i, response in enumerate(responses):
            assert response.status_code == 200
            result = response.json()
            assert result.get("id") == 100 + i
            assert "error" not in result