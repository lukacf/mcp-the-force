"""
Integration tests for error handling scenarios.
"""
import pytest
from unittest.mock import patch, Mock
from mcp_second_brain.tools.integration import execute_tool_direct
from mcp_second_brain.adapters import get_adapter


class TestErrorHandlingIntegration:
    """Test error handling across the system."""
    
    @pytest.mark.asyncio
    async def test_missing_api_key_error(self):
        """Test error when API key is missing."""
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}, clear=False):
            # Try to use OpenAI tool without key
            with pytest.raises(RuntimeError, match="API key|credentials"):
                await execute_tool_direct(
                    "chat_with_o3",
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="test"
                )
    
    @pytest.mark.asyncio
    async def test_invalid_model_name(self):
        """Test error with invalid model configuration."""
        # This would happen if someone modified the tool definitions incorrectly
        with patch('mcp_second_brain.tools.definitions.ChatWithO3.model_name', 'invalid-model'):
            with pytest.raises(Exception):  # Specific exception depends on implementation
                await execute_tool_direct(
                    "chat_with_o3",
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="test"
                )
    
    @pytest.mark.asyncio
    async def test_network_timeout(self, mock_openai_client):
        """Test handling of network timeouts."""
        # Simulate timeout
        mock_openai_client.beta.chat.completions.parse.side_effect = TimeoutError("Request timed out")
        
        with pytest.raises(TimeoutError):
            await execute_tool_direct(
                "chat_with_o3",
                instructions="Test",
                output_format="text",
                context=[],
                session_id="test"
            )
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mock_openai_client):
        """Test handling of rate limit errors."""
        # Simulate rate limit error
        error = Exception("Rate limit exceeded")
        error.status_code = 429
        mock_openai_client.beta.chat.completions.parse.side_effect = error
        
        with pytest.raises(Exception, match="Rate limit"):
            await execute_tool_direct(
                "chat_with_o3",
                instructions="Test",
                output_format="text",
                context=[],
                session_id="test"
            )
    
    @pytest.mark.asyncio
    async def test_invalid_parameter_types(self):
        """Test type validation for parameters."""
        # Wrong type for context (should be list)
        with pytest.raises(ValueError, match="Invalid type|context"):
            await execute_tool_direct(
                "chat_with_gemini25_flash",
                instructions="Test",
                output_format="text",
                context="not-a-list"  # Should be list
            )
        
        # Wrong type for temperature
        with pytest.raises(ValueError, match="Invalid type|temperature"):
            await execute_tool_direct(
                "chat_with_gemini25_flash",
                instructions="Test",
                output_format="text",
                context=[],
                temperature="high"  # Should be float
            )
    
    @pytest.mark.asyncio
    async def test_file_not_found_in_context(self):
        """Test handling of non-existent files in context."""
        # This should not crash, just skip the file
        result = await execute_tool_direct(
            "chat_with_gemini25_flash",
            instructions="Analyze these files",
            output_format="text",
            context=["/path/that/does/not/exist.py"]
        )
        
        # Should still work but with empty context
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_oversized_prompt(self, tmp_path, mock_openai_client):
        """Test handling of prompts that exceed model limits."""
        # Create a massive context
        huge_file = tmp_path / "huge.txt"
        huge_file.write_text("x" * 10_000_000)  # 10MB file
        
        # Mock response for when it eventually works
        mock_openai_client.beta.chat.completions.parse.return_value = Mock(
            choices=[Mock(message=Mock(parsed=Mock(response="Handled"), refusal=None))]
        )
        
        # This should either:
        # 1. Automatically use vector store
        # 2. Truncate the context
        # 3. Raise a clear error
        # But should NOT crash or hang
        
        try:
            result = await execute_tool_direct(
                "chat_with_o3",
                instructions="Analyze",
                output_format="text",
                context=[str(huge_file)],
                session_id="test"
            )
            # If it succeeds, it should have handled the size somehow
            assert result == "Handled"
        except ValueError as e:
            # Or it should raise a clear error about size
            assert "size" in str(e).lower() or "large" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_malformed_response_from_api(self, mock_openai_client):
        """Test handling of malformed API responses."""
        # Return None instead of proper response
        mock_openai_client.beta.chat.completions.parse.return_value = None
        
        with pytest.raises(Exception):  # Should raise some error
            await execute_tool_direct(
                "chat_with_o3",
                instructions="Test",
                output_format="text",
                context=[],
                session_id="test"
            )
    
    @pytest.mark.asyncio
    async def test_adapter_initialization_failure(self):
        """Test handling of adapter initialization failures."""
        with patch('mcp_second_brain.adapters.vertex_adapter.VertexAdapter.__init__') as mock_init:
            mock_init.side_effect = Exception("Failed to initialize Vertex client")
            
            with pytest.raises(RuntimeError, match="Failed to create adapter"):
                await execute_tool_direct(
                    "chat_with_gemini25_flash",
                    instructions="Test",
                    output_format="text",
                    context=[]
                )
    
    @pytest.mark.asyncio
    async def test_concurrent_error_isolation(self, mock_openai_client, mock_vertex_client):
        """Test that errors in one tool don't affect others."""
        import asyncio
        
        # Make one succeed and one fail
        mock_openai_client.beta.chat.completions.parse.return_value = Mock(
            choices=[Mock(message=Mock(parsed=Mock(response="Success"), refusal=None))]
        )
        mock_vertex_client.generate_content.side_effect = Exception("Vertex failed")
        
        # Run both concurrently
        tasks = [
            execute_tool_direct(
                "chat_with_o3",
                instructions="Should succeed",
                output_format="text",
                context=[],
                session_id="test"
            ),
            execute_tool_direct(
                "chat_with_gemini25_flash",
                instructions="Should fail",
                output_format="text",
                context=[]
            )
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # First should succeed
        assert results[0] == "Success"
        
        # Second should be an exception
        assert isinstance(results[1], Exception)
        assert "Vertex failed" in str(results[1])