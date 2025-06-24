"""
Integration tests for complete tool execution flows.
"""
import pytest
from unittest.mock import Mock
import json


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
    async def test_openai_tool_with_session(self, run_tool, parse_adapter_response):
        """Test OpenAI tool with session continuity."""
        # First call
        result1 = await run_tool(
            "chat_with_o3",
            instructions="I need help with Python async programming",
            output_format="explanation",
            context=[],
            session_id="test-session-1"
        )
        
        data1 = parse_adapter_response(result1)
        assert data1["mock"] is True
        assert data1["model"] == "o3"
        assert "Python async programming" in data1["prompt_preview"]
        
        # Second call with same session
        result2 = await run_tool(
            "chat_with_o3",
            instructions="Show me an example",
            output_format="code",
            context=[],
            session_id="test-session-1"
        )
        
        data2 = parse_adapter_response(result2)
        assert data2["mock"] is True
        assert data2["model"] == "o3"
        assert "Show me an example" in data2["prompt_preview"]
        # Note: Session continuity is handled by the adapter, we just verify the call went through
    
    @pytest.mark.asyncio
    async def test_large_context_triggers_vector_store(self, temp_project, mock_openai_client, run_tool, parse_adapter_response):
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
        
        # Vector store creation will be handled by the mock client
        
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
        
        # Parse the mock response
        data = parse_adapter_response(result)
        assert data["mock"] is True
        assert data["model"] == "gpt-4.1"
        assert "Analyze this large codebase" in data["prompt_preview"]
        # Vector store should have been created
        assert data["vector_store_ids"] is not None
        assert len(data["vector_store_ids"]) > 0
        # Also verify the mock client was called
        mock_openai_client.vector_stores.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_mixed_parameters_routing(self, mock_openai_client, run_tool, parse_adapter_response, tmp_path):
        """Test that all parameter types route correctly."""
        # Create a real file for attachments
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")
        
        # Mock vector store creation
        mock_openai_client.vector_stores.create.return_value = Mock(id="vs_params")
        mock_openai_client.vector_stores.file_batches.upload_and_poll.return_value = Mock(
            status="completed"
        )
        
        result = await run_tool(
            "chat_with_gpt4_1",
            instructions="Test with all param types",
            output_format="json",
            context=[],
            temperature=0.8,  # adapter param
            session_id="test-params",  # session param
            attachments=[str(test_file)]  # vector_store param with real file
        )
        
        # Verify parameters were routed correctly
        data = parse_adapter_response(result)
        assert data["mock"] is True
        assert data["model"] == "gpt-4.1"
        assert data["adapter_kwargs"]["temperature"] == 0.8
        # Vector store should be created for attachments
        # Note: May include auto-attached memory stores
        assert "vs_params" in data["vector_store_ids"]
    
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
    async def test_concurrent_tool_execution(self, run_tool, parse_adapter_response):
        """Test that multiple tools can execute concurrently."""
        import asyncio
        
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
        
        # Parse results and verify mix of models
        parsed_results = [parse_adapter_response(r) for r in results]
        openai_results = [r for r in parsed_results if r["model"] == "o3"]
        vertex_results = [r for r in parsed_results if r["model"] == "gemini-2.5-flash"]
        
        assert len(openai_results) == 3
        assert len(vertex_results) == 3
        
        # All should be mock responses
        assert all(r["mock"] is True for r in parsed_results)