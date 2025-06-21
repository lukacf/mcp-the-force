"""
Integration tests for error handling scenarios.
"""
import pytest
from unittest.mock import patch, Mock
from mcp_second_brain.tools.executor import executor
from mcp_second_brain.tools.registry import get_tool
# Import definitions to ensure tools are registered
import mcp_second_brain.tools.definitions  # noqa: F401


class TestErrorHandlingIntegration:
    """Test error handling across the system."""
    
    @pytest.mark.asyncio
    async def test_missing_api_key_error(self):
        """Test error when API key is missing."""
        from mcp_second_brain.config import get_settings
        
        # Clear the settings cache
        get_settings.cache_clear()
        
        try:
            with patch.dict('os.environ', {'OPENAI_API_KEY': ''}, clear=False):
                # Try to use OpenAI tool without key
                with pytest.raises(ValueError, match="API_KEY|credentials"):
                    tool_metadata = get_tool("chat_with_o3")
                    if not tool_metadata:
                        raise ValueError("Tool chat_with_o3 not found")
                    await executor.execute(
                        tool_metadata,
                        instructions="Test",
                        output_format="text",
                        context=[],
                        session_id="test"
                    )
        finally:
            # Clear cache again to avoid affecting other tests
            get_settings.cache_clear()
    
    @pytest.mark.asyncio
    async def test_invalid_model_name(self, mock_env, mock_openai_client):
        """Test error with invalid model configuration."""
        # Simulate OpenAI API rejecting invalid model
        mock_openai_client.responses.create.side_effect = Exception("The model `invalid-model` does not exist")
        
        # This would happen if someone modified the tool definitions incorrectly
        with patch('mcp_second_brain.tools.definitions.ChatWithO3.model_name', 'invalid-model'):
            with pytest.raises(Exception, match="model.*does not exist|invalid.*model"):  # Specific exception depends on implementation
                tool_metadata = get_tool("chat_with_o3")
                if not tool_metadata:
                    raise ValueError("Tool chat_with_o3 not found")
                await executor.execute(
                    tool_metadata,
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="test"
                )
    
    @pytest.mark.asyncio
    async def test_network_timeout(self, mock_env, mock_openai_client):
        """Test handling of network timeouts."""
        # Simulate timeout
        mock_openai_client.responses.create.side_effect = TimeoutError("Request timed out")
        
        with pytest.raises(TimeoutError):
            tool_metadata = get_tool("chat_with_o3")
            if not tool_metadata:
                raise ValueError("Tool chat_with_o3 not found")
            await executor.execute(
                tool_metadata,
                instructions="Test",
                output_format="text",
                context=[],
                session_id="test"
            )
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mock_env, mock_openai_client):
        """Test handling of rate limit errors."""
        # Simulate rate limit error
        error = Exception("Rate limit exceeded")
        error.status_code = 429
        mock_openai_client.responses.create.side_effect = error
        
        with pytest.raises(Exception, match="Rate limit"):
            tool_metadata = get_tool("chat_with_o3")
            if not tool_metadata:
                raise ValueError("Tool chat_with_o3 not found")
            await executor.execute(
                tool_metadata,
                instructions="Test",
                output_format="text",
                context=[],
                session_id="test"
            )
    
    @pytest.mark.asyncio
    async def test_invalid_parameter_types(self):
        """Test type validation for parameters."""
        # Wrong type for context (should be list)
        with pytest.raises(TypeError, match="context.*expected list"):
            tool_metadata = get_tool("chat_with_gemini25_flash")
            if not tool_metadata:
                raise ValueError("Tool chat_with_gemini25_flash not found")
            await executor.execute(
                tool_metadata,
                instructions="Test",
                output_format="text",
                context="not-a-list"  # Should be list
            )
        
        # Wrong type for temperature
        with pytest.raises(TypeError, match="temperature.*expected.*float"):
            tool_metadata = get_tool("chat_with_gemini25_flash")
            if not tool_metadata:
                raise ValueError("Tool chat_with_gemini25_flash not found")
            await executor.execute(
                tool_metadata,
                instructions="Test",
                output_format="text",
                context=[],
                temperature="high"  # Should be float
            )
    
    @pytest.mark.asyncio
    async def test_file_not_found_in_context(self, mock_env):
        """Test handling of non-existent files in context."""
        # This should not crash, just skip the file
        tool_metadata = get_tool("chat_with_gemini25_flash")
        if not tool_metadata:
            raise ValueError("Tool chat_with_gemini25_flash not found")
        result = await executor.execute(
            tool_metadata,
            instructions="Analyze these files",
            output_format="text",
            context=["/path/that/does/not/exist.py"]
        )
        
        # Should still work but with empty context
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_oversized_prompt(self, tmp_path, mock_env, mock_openai_client):
        """Test handling of prompts that exceed model limits."""
        # Create a massive context
        huge_file = tmp_path / "huge.txt"
        huge_file.write_text("x" * 10_000_000)  # 10MB file
        
        # Mock response for when it eventually works
        mock_openai_client.responses.create.return_value = Mock(id="resp_test", output_text="Handled")
        
        # This should either:
        # 1. Automatically use vector store
        # 2. Truncate the context
        # 3. Raise a clear error
        # But should NOT crash or hang
        
        try:
            tool_metadata = get_tool("chat_with_o3")
            if not tool_metadata:
                raise ValueError("Tool chat_with_o3 not found")
            result = await executor.execute(
                tool_metadata,
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
    async def test_malformed_response_from_api(self, mock_env, mock_openai_client):
        """Test handling of malformed API responses."""
        # Return None instead of proper response
        mock_openai_client.responses.create.return_value = None
        
        with pytest.raises(Exception):  # Should raise some error
            tool_metadata = get_tool("chat_with_o3")
            if not tool_metadata:
                raise ValueError("Tool chat_with_o3 not found")
            await executor.execute(
                tool_metadata,
                instructions="Test",
                output_format="text",
                context=[],
                session_id="test"
            )
    
    @pytest.mark.asyncio
    async def test_adapter_initialization_failure(self):
        """Test handling of adapter initialization failures."""
        # Patch get_adapter to return an error
        with patch('mcp_second_brain.adapters.get_adapter') as mock_get_adapter:
            mock_get_adapter.return_value = (None, "Failed to initialize adapter: Test error")
            
            # Executor returns an error string when adapter init fails
            tool_metadata = get_tool("chat_with_gemini25_flash")
            if not tool_metadata:
                raise ValueError("Tool chat_with_gemini25_flash not found")
            result = await executor.execute(
                tool_metadata,
                instructions="Test",
                output_format="text",
                context=[]
            )
            assert "Failed to initialize adapter" in result
    
    @pytest.mark.asyncio
    async def test_concurrent_error_isolation(self, mock_env, mock_openai_client, mock_vertex_client):
        """Test that errors in one tool don't affect others."""
        import asyncio
        
        # Make one succeed and one fail
        mock_openai_client.responses.create.return_value = Mock(output_text="Success", id="resp_test")
        mock_vertex_client.models.generate_content_stream.side_effect = Exception("Vertex failed")
        
        # Run both concurrently
        o3_metadata = get_tool("chat_with_o3")
        gemini_metadata = get_tool("chat_with_gemini25_flash")
        if not o3_metadata or not gemini_metadata:
            raise ValueError("Required tools not found")
        
        tasks = [
            executor.execute(
                o3_metadata,
                instructions="Should succeed",
                output_format="text",
                context=[],
                session_id="test"
            ),
            executor.execute(
                gemini_metadata,
                instructions="Should fail",
                output_format="text",
                context=[]
            )
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # First should succeed
        assert results[0] == "Success"
        
        # Second should fail - could be exception or error string
        if isinstance(results[1], Exception):
            assert "Vertex failed" in str(results[1])
        else:
            assert isinstance(results[1], str)
            assert "Error" in results[1] or "failed" in results[1]