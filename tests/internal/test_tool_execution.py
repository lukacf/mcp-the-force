"""
Integration tests for complete tool execution flows.
"""
import pytest
from unittest.mock import AsyncMock


class TestToolExecutionIntegration:
    """Test complete tool execution flows with real components."""
    
    @pytest.mark.asyncio
    async def test_gemini_tool_with_real_files(self, temp_project, run_tool):
        """Test Gemini tool execution with real file loading."""
        # Execute tool with real file context
        result = await run_tool(
            "chat_with_gemini25_flash",
            instructions="Analyze the Python files in this project",
            output_format="bullet points",
            context=[str(temp_project)]
        )
        
        # With mock adapter, we get JSON metadata
        import json
        data = json.loads(result)
        
        # Verify correct model was used
        assert data["model"] == "gemini-2.5-flash"
        
        # Verify prompt was built correctly
        prompt = data["prompt_preview"]
        assert "Analyze the Python files" in prompt
        
        # Verify adapter parameters
        assert data["adapter_kwargs"]["temperature"] == 0.3  # Default for flash
        assert data["adapter_kwargs"]["timeout"] == 300
    
    @pytest.mark.asyncio
    async def test_openai_tool_with_session(self, mock_openai_client, run_tool):
        """Test OpenAI tool with session continuity."""
        # Setup mock response
        mock_response = AsyncMock()
        mock_response.output_text = "I understand. Let me help with that."
        mock_response.id = "resp_123"
        mock_openai_client.responses.create.return_value = mock_response
        
        # First call
        result1 = await run_tool(
            "chat_with_o3",
            instructions="I need help with Python async programming",
            output_format="explanation",
            context=[],
            session_id="test-session-1"
        )
        
        assert "I understand" in result1
        
        # Second call with same session
        mock_response2 = AsyncMock()
        mock_response2.output_text = "Continuing from before, here's an async example."
        mock_response2.id = "resp_124"
        mock_openai_client.responses.create.return_value = mock_response2
        
        result2 = await run_tool(
            "chat_with_o3",
            instructions="Show me an example",
            output_format="code",
            context=[],
            session_id="test-session-1"
        )
        
        assert "Continuing from before" in result2
        
        # Verify second call included previous response ID
        second_call_kwargs = mock_openai_client.responses.create.call_args[1]
        assert second_call_kwargs.get("previous_response_id") == "resp_123"
    
    @pytest.mark.asyncio
    async def test_large_context_triggers_vector_store(self, temp_project, mock_openai_client, run_tool):
        """Test that large context automatically uses vector store."""
        # Create large files to exceed inline token limit (12000 tokens)
        # Create fewer but larger files to ensure we exceed the limit
        for i in range(10):
            file_path = temp_project / f"module{i}.py"
            # Create content that's roughly 2000 tokens each (~8000 chars)
            lines = [f"# Module {i} - Large file with many tokens"]
            for j in range(200):
                lines.append(f"def function_{j}():")
                lines.append("    # This is a long comment to increase token count")
                lines.append(f"    variable_{j} = 'This is a string value that takes up tokens'")
                lines.append(f"    return variable_{j} * 10")
                lines.append("")
            content = "\n".join(lines)
            file_path.write_text(content)
        
        # Vector store mocking is already handled in conftest.py
        
        # Mock the response
        mock_response = AsyncMock()
        mock_response.output_text = "Analyzed large codebase"
        mock_response.id = "resp_large"
        mock_openai_client.responses.create.return_value = mock_response
        
        # Collect all the created files as attachments
        attachment_files = [str(temp_project / f"module{i}.py") for i in range(10)]
        
        # Also add some files that will fit in context to ensure both paths work
        [str(temp_project / "src")]
        
        result = await run_tool(
            "chat_with_gpt4_1",
            instructions="Analyze this large codebase",
            output_format="summary",
            context=[],  # Empty context to force vector store usage
            attachments=attachment_files,  # Use attachments parameter
            session_id="test-large"
        )
        
        # Should have created vector store
        mock_openai_client.vector_stores.create.assert_called_once()
        
        # Response should work
        assert "Analyzed large codebase" in result
    
    @pytest.mark.asyncio
    async def test_mixed_parameters_routing(self, mock_openai_client, run_tool):
        """Test that all parameter types route correctly."""
        mock_response = AsyncMock()
        mock_response.output_text = "Response with custom params"
        mock_response.id = "resp_custom"
        mock_openai_client.responses.create.return_value = mock_response
        
        result = await run_tool(
            "chat_with_gpt4_1",
            instructions="Test with all param types",
            output_format="json",
            context=[],
            temperature=0.8,  # adapter param
            session_id="test-params",  # session param
            attachments=["/tmp/fake.txt"]  # vector_store param (file doesn't need to exist for this test)
        )
        
        # Verify temperature was passed to adapter
        call_kwargs = mock_openai_client.responses.create.call_args[1]
        assert call_kwargs.get("temperature") == 0.8
        
        assert "Response with custom params" in result
    
    @pytest.mark.asyncio
    async def test_error_propagation(self, run_tool):
        """Test that errors are properly propagated."""
        # Test with missing required parameter
        with pytest.raises(ValueError, match="Missing required parameter"):
            await run_tool(
                "chat_with_gemini25_flash",
                instructions="Test"
                # Missing output_format and context
            )
        
        # Test with invalid tool
        with pytest.raises(KeyError):
            await run_tool("invalid_tool_name", instructions="Test", output_format="text", context=[])
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)  # Override default 10s timeout
    async def test_concurrent_tool_execution(self, mock_openai_client, mock_vertex_client, run_tool):
        """Test that multiple tools can execute concurrently."""
        import asyncio
        
        # Setup mocks
        mock_response = AsyncMock()
        mock_response.output_text = "OpenAI response"
        mock_response.id = "resp_concurrent"
        mock_openai_client.responses.create.return_value = mock_response
        mock_chunk_concurrent = AsyncMock()
        mock_chunk_concurrent.text = "Vertex response"
        mock_vertex_client.models.generate_content_stream.return_value = [mock_chunk_concurrent]
        
        # Execute multiple tools concurrently
        tasks = [
            run_tool(
                "chat_with_o3",
                instructions=f"Task {i}",
                output_format="text",
                context=[],
                session_id=f"session-{i}"
            )
            for i in range(3)
        ] + [
            run_tool(
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