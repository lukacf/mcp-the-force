"""
Integration tests for complete tool execution flows.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from mcp_second_brain.tools.executor import ToolExecutor
from mcp_second_brain.tools.integration import execute_tool_direct


class TestToolExecutionIntegration:
    """Test complete tool execution flows with real components."""
    
    @pytest.mark.asyncio
    async def test_gemini_tool_with_real_files(self, temp_project, mock_vertex_client):
        """Test Gemini tool execution with real file loading."""
        # Mock the Vertex client to return a response
        mock_vertex_client.generate_content.return_value.text = "Analysis of your Python code:\n- Uses print function\n- Simple structure"
        
        # Execute tool with real file context
        result = await execute_tool_direct(
            "chat_with_gemini25_flash",
            instructions="Analyze the Python files in this project",
            output_format="bullet points",
            context=[str(temp_project)]
        )
        
        # Verify response
        assert "Analysis of your Python code" in result
        assert "print function" in result
        
        # Verify the prompt included file contents
        call_args = mock_vertex_client.generate_content.call_args
        prompt = call_args[0][0]
        
        # Should include file contents from temp_project
        assert "main.py" in prompt
        assert "print('hello')" in prompt
        assert "utils.py" in prompt
        assert "def helper():" in prompt
        
        # Should respect .gitignore
        assert "debug.log" not in prompt
        assert "__pycache__" not in prompt
    
    @pytest.mark.asyncio
    async def test_openai_tool_with_session(self, mock_openai_client):
        """Test OpenAI tool with session continuity."""
        # Setup mock response
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock(
            message=AsyncMock(
                parsed=AsyncMock(response="I understand. Let me help with that."),
                refusal=None
            )
        )]
        mock_response.id = "resp_123"
        mock_openai_client.beta.chat.completions.parse.return_value = mock_response
        
        # First call
        result1 = await execute_tool_direct(
            "chat_with_o3",
            instructions="I need help with Python async programming",
            output_format="explanation",
            context=[],
            session_id="test-session-1"
        )
        
        assert "I understand" in result1
        
        # Second call with same session
        mock_response2 = AsyncMock()
        mock_response2.choices = [AsyncMock(
            message=AsyncMock(
                parsed=AsyncMock(response="Continuing from before, here's an async example."),
                refusal=None
            )
        )]
        mock_response2.id = "resp_124"
        mock_openai_client.beta.chat.completions.parse.return_value = mock_response2
        
        result2 = await execute_tool_direct(
            "chat_with_o3",
            instructions="Show me an example",
            output_format="code",
            context=[],
            session_id="test-session-1"
        )
        
        assert "Continuing from before" in result2
        
        # Verify second call included previous response ID
        second_call_kwargs = mock_openai_client.beta.chat.completions.parse.call_args[1]
        assert second_call_kwargs.get("metadata", {}).get("previous_response_id") == "resp_123"
    
    @pytest.mark.asyncio
    async def test_large_context_triggers_vector_store(self, temp_project, mock_openai_client):
        """Test that large context automatically uses vector store."""
        # Create many files to exceed inline token limit
        for i in range(50):
            file_path = temp_project / f"module{i}.py"
            file_path.write_text(f"# Module {i}\n" + "x" * 1000)  # ~1KB each
        
        # Mock vector store creation
        mock_openai_client.beta.vector_stores.create.return_value.id = "vs_test"
        mock_openai_client.beta.vector_stores.file_batches.upload_and_poll.return_value.status = "completed"
        
        # Mock the response
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock(
            message=AsyncMock(
                parsed=AsyncMock(response="Analyzed large codebase"),
                refusal=None
            )
        )]
        mock_openai_client.beta.chat.completions.parse.return_value = mock_response
        
        result = await execute_tool_direct(
            "chat_with_gpt4_1",
            instructions="Analyze this large codebase",
            output_format="summary",
            context=[str(temp_project)],
            session_id="test-large"
        )
        
        # Should have created vector store
        mock_openai_client.beta.vector_stores.create.assert_called_once()
        
        # Response should work
        assert "Analyzed large codebase" in result
    
    @pytest.mark.asyncio
    async def test_mixed_parameters_routing(self, mock_openai_client):
        """Test that all parameter types route correctly."""
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock(
            message=AsyncMock(
                parsed=AsyncMock(response="Response with custom params"),
                refusal=None
            )
        )]
        mock_openai_client.beta.chat.completions.parse.return_value = mock_response
        
        result = await execute_tool_direct(
            "chat_with_gpt4_1",
            instructions="Test with all param types",
            output_format="json",
            context=[],
            temperature=0.8,  # adapter param
            session_id="test-params",  # session param
            attachments=["/tmp/fake.txt"]  # vector_store param (file doesn't need to exist for this test)
        )
        
        # Verify temperature was passed to adapter
        call_kwargs = mock_openai_client.beta.chat.completions.parse.call_args[1]
        assert call_kwargs.get("temperature") == 0.8
        
        assert "Response with custom params" in result
    
    @pytest.mark.asyncio
    async def test_error_propagation(self):
        """Test that errors are properly propagated."""
        # Test with missing required parameter
        with pytest.raises(ValueError, match="Missing required parameter"):
            await execute_tool_direct(
                "chat_with_gemini25_flash",
                instructions="Test"
                # Missing output_format and context
            )
        
        # Test with invalid tool
        with pytest.raises(ValueError, match="Unknown tool"):
            await execute_tool_direct(
                "invalid_tool_name",
                instructions="Test",
                output_format="text",
                context=[]
            )
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)  # Override default 10s timeout
    async def test_concurrent_tool_execution(self, mock_openai_client, mock_vertex_client):
        """Test that multiple tools can execute concurrently."""
        import asyncio
        
        # Setup mocks
        mock_openai_client.beta.chat.completions.parse.return_value = AsyncMock(
            choices=[AsyncMock(message=AsyncMock(
                parsed=AsyncMock(response="OpenAI response"),
                refusal=None
            ))]
        )
        mock_vertex_client.generate_content.return_value.text = "Vertex response"
        
        # Execute multiple tools concurrently
        tasks = [
            execute_tool_direct(
                "chat_with_o3",
                instructions=f"Task {i}",
                output_format="text",
                context=[],
                session_id=f"session-{i}"
            )
            for i in range(3)
        ] + [
            execute_tool_direct(
                "chat_with_gemini25_flash",
                instructions=f"Task {i}",
                output_format="text",
                context=[]
            )
            for i in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Should have 6 results
        assert len(results) == 6
        
        # Should have mix of responses
        openai_results = [r for r in results if "OpenAI" in r]
        vertex_results = [r for r in results if "Vertex" in r]
        
        assert len(openai_results) == 3
        assert len(vertex_results) == 3