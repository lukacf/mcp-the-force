"""
Integration tests for complete tool execution flows.
"""

import pytest
from unittest.mock import Mock
import json
import fastmcp.exceptions


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
            context=[str(temp_project)],
            session_id="gemini-real-files",
        )

        # With mock adapter, we get JSON metadata
        data = json.loads(result)

        # Verify correct model was used
        assert data["model"] == "gemini-2.5-flash"

        # Verify prompt was built correctly
        prompt = data["prompt_preview"]
        assert "Analyze the Python files" in prompt

        # Verify adapter parameters
        assert (
            data["adapter_kwargs"]["temperature"] == 1.0
        )  # Default for flash (updated)
        assert (
            data["adapter_kwargs"]["timeout"] == 600
        )  # Updated default for heavyweight models

    @pytest.mark.asyncio
    async def test_openai_tool_with_session(self, run_tool, parse_adapter_response):
        """Test OpenAI tool with session continuity."""
        # First call
        result1 = await run_tool(
            "chat_with_gpt52_pro",
            instructions="I need help with Python async programming",
            output_format="explanation",
            context=[],
            session_id="test-session-1",
        )

        data1 = parse_adapter_response(result1)
        assert data1["mock"] is True
        assert data1["model"] == "gpt-5.2-pro"
        assert "Python async programming" in data1["prompt"]

        # Second call with same session
        result2 = await run_tool(
            "chat_with_gpt52_pro",
            instructions="Show me an example",
            output_format="code",
            context=[],
            session_id="test-session-1",
        )

        data2 = parse_adapter_response(result2)
        assert data2["mock"] is True
        assert data2["model"] == "gpt-5.2-pro"
        assert "Show me an example" in data2["prompt"]
        # Note: Session continuity is handled by the adapter, we just verify the call went through

    @pytest.mark.asyncio
    async def test_large_context_triggers_vector_store(
        self, temp_project, mock_openai_factory, run_tool, parse_adapter_response
    ):
        """Test that large context automatically uses vector store."""
        from unittest.mock import patch, AsyncMock

        # Create test files
        test_file = temp_project / "test.py"
        test_file.write_text("def hello(): pass")

        # Mock the TokenBudgetOptimizer to simulate overflow
        with patch(
            "mcp_the_force.optimization.token_budget_optimizer.TokenBudgetOptimizer"
        ) as mock_optimizer_class:
            # Create mock optimizer instance
            mock_optimizer = AsyncMock()
            mock_optimizer_class.return_value = mock_optimizer

            # Create mock optimization plan with overflow
            from mcp_the_force.optimization.models import Plan, FileInfo

            mock_plan = Plan(
                inline_files=[],  # Empty - all files overflowed
                overflow_files=[
                    FileInfo(
                        path=str(test_file), content="", size=100, tokens=50, mtime=0
                    )
                ],  # Files that overflowed
                file_tree="📁 test.py (attached)",
                optimized_prompt="<instructions>\nAnalyze the large project\n</instructions>\n\n<output_format>\nsummary\n</output_format>",
                messages=[
                    {"role": "developer", "content": "Test developer prompt"},
                    {"role": "user", "content": "Analyze the large project"},
                ],
                total_prompt_tokens=1500,
                iterations=1,
                overflow_paths=[str(test_file)],  # For backward compatibility
            )
            mock_optimizer.optimize.return_value = mock_plan

            # Mock vector store creation
            mock_vs_manager = AsyncMock()
            mock_vs_manager.create = AsyncMock(return_value={"store_id": "vs-test-id"})

            # Also mock memory storage to prevent real async calls
            # Import the executor to patch its vector_store_manager
            from mcp_the_force.tools.executor import executor

            with (
                patch.object(executor, "vector_store_manager", mock_vs_manager),
                patch(
                    "mcp_the_force.tools.safe_history.safe_record_conversation",
                    new_callable=AsyncMock,
                ),
            ):
                result = await run_tool(
                    "chat_with_gpt41",
                    instructions="Analyze this large codebase",
                    output_format="summary",
                    context=[str(temp_project)],
                    session_id="test-large",
                )

                # Verify vector store was created with overflow files
                # The call now includes provider parameter
                mock_vs_manager.create.assert_called_once_with(
                    [str(test_file)], session_id="test-large", provider="openai"
                )

                # Parse the mock response
                data = parse_adapter_response(result)
                assert data["mock"] is True
                assert data["model"] == "gpt-4.1"
                # Vector store should have been passed to adapter
                assert data["vector_store_ids"] == ["vs-test-id"]

    @pytest.mark.asyncio
    async def test_mixed_parameters_routing(
        self, mock_openai_factory, run_tool, parse_adapter_response, tmp_path
    ):
        """Test that all parameter types route correctly."""
        # Create a real file for attachments
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        # Mock vector store creation
        mock_openai_factory.vector_stores.create.return_value = Mock(id="vs_params")
        mock_openai_factory.vector_stores.file_batches.upload_and_poll.return_value = (
            Mock(status="completed", file_counts=Mock(completed=1, failed=0, total=1))
        )

        result = await run_tool(
            "chat_with_gpt41",
            instructions="Test with all param types",
            output_format="json",
            context=[str(test_file)],  # context with real file
            temperature=0.8,  # adapter param
            session_id="test-params",  # session param
        )

        # Verify parameters were routed correctly
        data = parse_adapter_response(result)
        assert data["mock"] is True
        assert data["model"] == "gpt-4.1"
        assert data["adapter_kwargs"]["temperature"] == 0.8
        # With small files, no vector store should be created (files fit in context)
        # But memory stores might be auto-attached
        # So we just verify the parameter routing worked

    @pytest.mark.asyncio
    async def test_error_propagation(self, run_tool):
        """Test that errors are properly propagated."""
        # Test with missing required parameter
        with pytest.raises(
            fastmcp.exceptions.ToolError, match="Missing required parameter"
        ):
            await run_tool(
                "chat_with_gemini25_flash",
                instructions="Test",
                # Missing output_format and context
            )

        # Test with invalid tool
        with pytest.raises(KeyError):
            await run_tool(
                "invalid_tool_name",
                instructions="Test",
                output_format="text",
                context=[],
            )

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)  # Override default 10s timeout
    async def test_concurrent_tool_execution(self, run_tool, parse_adapter_response):
        """Test that multiple tools can execute concurrently."""
        import asyncio

        # Execute multiple tools concurrently
        tasks = [
            run_tool(
                "chat_with_gpt52_pro",
                instructions=f"Task {i}",
                output_format="text",
                context=[],
                session_id=f"session-{i}",
            )
            for i in range(3)
        ] + [
            run_tool(
                "chat_with_gemini25_flash",
                instructions=f"Task {i}",
                output_format="text",
                context=[],
                session_id=f"gemini-{i}",
            )
            for i in range(3)
        ]

        results = await asyncio.gather(*tasks)

        # Should have 6 results
        assert len(results) == 6

        # Parse results and verify mix of models
        parsed_results = [parse_adapter_response(r) for r in results]
        openai_results = [r for r in parsed_results if r["model"] == "gpt-5.2-pro"]
        vertex_results = [r for r in parsed_results if r["model"] == "gemini-2.5-flash"]

        assert len(openai_results) == 3
        assert len(vertex_results) == 3

        # All should be mock responses
        assert all(r["mock"] is True for r in parsed_results)
