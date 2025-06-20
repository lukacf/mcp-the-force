"""
Unit tests for ToolExecutor orchestration.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from mcp_second_brain.tools.executor import ToolExecutor
from mcp_second_brain.tools.definitions import ChatWithGemini25Flash, ChatWithO3
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
    async def test_execute_gemini_tool(self, executor, mock_adapter, tmp_path):
        """Test executing a Gemini tool with proper parameter routing."""
        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        
        # Mock the adapter creation
        with patch('mcp_second_brain.adapters.get_adapter') as mock_get_adapter:
            mock_get_adapter.return_value = (mock_adapter, None)
            
            result = await executor.execute_tool(
                "chat_with_gemini25_flash",
                instructions="Explain this code",
                output_format="markdown",
                context=[str(test_file)],
                temperature=0.5
            )
        
        # Verify adapter was called with correct params
        mock_adapter.generate.assert_called_once()
        call_args = mock_adapter.generate.call_args
        
        # Check prompt was built
        prompt = call_args[0][0]
        assert "Explain this code" in prompt
        assert "markdown" in prompt
        assert "print('hello')" in prompt  # File content should be inlined
        
        # Check adapter params
        adapter_params = call_args[1]
        assert adapter_params.get("temperature") == 0.5
        
        # Check result
        assert result == "Mock response"
    
    @pytest.mark.asyncio
    async def test_execute_openai_tool_with_session(self, executor, mock_adapter):
        """Test executing an OpenAI tool with session support."""
        with patch('mcp_second_brain.adapters.get_adapter') as mock_get_adapter:
            mock_get_adapter.return_value = (mock_adapter, None)
            
            # Mock session cache
            with patch('mcp_second_brain.session_cache.get_session_cache') as mock_cache:
                cache = Mock()
                cache.get.return_value = "previous_response_id"
                mock_cache.return_value = cache
                
                result = await executor.execute_tool(
                    "chat_with_o3",
                    instructions="Continue our discussion",
                    output_format="text",
                    context=[],
                    session_id="test-session",
                    reasoning_effort="high"
                )
        
        # Verify session was used
        cache.get.assert_called_with("test-session")
        
        # Verify adapter params include reasoning_effort
        call_args = mock_adapter.generate.call_args
        adapter_params = call_args[1]
        assert adapter_params.get("reasoning_effort") == "high"
    
    @pytest.mark.asyncio
    async def test_vector_store_routing(self, executor, mock_adapter, tmp_path):
        """Test that attachments parameter triggers vector store creation."""
        # Create large files to trigger vector store
        large_file = tmp_path / "large.txt"
        large_file.write_text("x" * 100_000)  # 100KB
        
        with patch('mcp_second_brain.adapters.get_adapter') as mock_get_adapter:
            mock_get_adapter.return_value = (mock_adapter, None)
            
            with patch('mcp_second_brain.tools.vector_store_manager.VectorStoreManager') as mock_vs:
                vs_manager = Mock()
                vs_manager.process_attachments = AsyncMock(return_value="vs_123")
                mock_vs.return_value = vs_manager
                
                result = await executor.execute_tool(
                    "chat_with_gpt4_1",
                    instructions="Analyze this",
                    output_format="text",
                    context=[],
                    attachments=[str(large_file)],
                    session_id="test"
                )
        
        # Verify vector store was created
        vs_manager.process_attachments.assert_called_once_with([str(large_file)])
    
    @pytest.mark.asyncio
    async def test_missing_required_parameter(self, executor):
        """Test that missing required parameter raises appropriate error."""
        with pytest.raises(ValueError, match="Missing required parameter"):
            await executor.execute_tool(
                "chat_with_gemini25_flash",
                instructions="Test"
                # Missing output_format and context
            )
    
    @pytest.mark.asyncio
    async def test_invalid_tool_name(self, executor):
        """Test that invalid tool name raises appropriate error."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await executor.execute_tool(
                "invalid_tool_name",
                instructions="Test",
                output_format="text",
                context=[]
            )
    
    @pytest.mark.asyncio
    async def test_adapter_error_handling(self, executor):
        """Test that adapter errors are handled gracefully."""
        with patch('mcp_second_brain.adapters.get_adapter') as mock_get_adapter:
            # Simulate adapter creation failure
            mock_get_adapter.return_value = (None, "Failed to create adapter: Invalid API key")
            
            with pytest.raises(RuntimeError, match="Failed to create adapter"):
                await executor.execute_tool(
                    "chat_with_gemini25_flash",
                    instructions="Test",
                    output_format="text",
                    context=[]
                )