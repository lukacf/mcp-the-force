"""
Unit tests for ToolExecutor orchestration.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from types import SimpleNamespace
import fastmcp.exceptions
from mcp_the_force.adapters.protocol import MCPAdapter, CallContext
from mcp_the_force.adapters.capabilities import AdapterCapabilities
# Don't import executor here - import after patching in tests


class TestToolExecutor:
    """Test the ToolExecutor orchestration."""

    @pytest.fixture
    def executor(self):
        """Create a ToolExecutor instance."""
        from mcp_the_force.tools.executor import ToolExecutor

        return ToolExecutor()

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter that satisfies MCPAdapter protocol."""
        adapter = MagicMock(spec=MCPAdapter)
        adapter.generate = AsyncMock(return_value={"content": "Mock response"})
        adapter.capabilities = AdapterCapabilities()
        adapter.param_class = MagicMock()
        adapter.display_name = "Mock Adapter"
        adapter.model_name = "mock-model"
        return adapter

    @pytest.fixture
    def mock_gemini_adapter(self):
        """Create a mock Gemini adapter with proper capabilities."""
        adapter = MagicMock(spec=MCPAdapter)
        adapter.generate = AsyncMock(return_value={"content": "Mock Gemini response"})
        # Gemini supports reasoning_effort
        adapter.capabilities = AdapterCapabilities(
            supports_reasoning_effort=True,
            supports_temperature=True,
            supports_structured_output=True,
        )
        adapter.param_class = MagicMock()
        adapter.display_name = "Mock Gemini Adapter"
        adapter.model_name = "gemini-2.5-flash"
        return adapter

    @pytest.fixture
    def mock_openai_adapter(self):
        """Create a mock OpenAI adapter with proper capabilities."""
        adapter = MagicMock(spec=MCPAdapter)
        adapter.generate = AsyncMock(return_value={"content": "Mock OpenAI response"})
        # O-series supports reasoning_effort but not temperature
        adapter.capabilities = AdapterCapabilities(
            supports_reasoning_effort=True,
            supports_temperature=False,  # O-series doesn't support temperature
            supports_structured_output=True,
            supports_web_search=True,
        )
        adapter.param_class = MagicMock()
        adapter.display_name = "Mock OpenAI Adapter"
        adapter.model_name = "o3"
        return adapter

    @pytest.mark.asyncio
    async def test_execute_gemini_tool(
        self, executor, mock_gemini_adapter, tmp_path, mock_env
    ):
        """Test executing a Gemini tool with proper parameter routing."""
        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # Mock the adapter registry to return a mock class that returns our mock adapter
        mock_adapter_class = MagicMock(return_value=mock_gemini_adapter)

        # Patch the registry and disable memory storage for unit test
        with (
            patch("mcp_the_force.tools.executor.get_adapter_class") as mock_get_class,
            patch(
                "mcp_the_force.memory.conversation.store_conversation_memory"
            ) as mock_store,
        ):
            mock_get_class.return_value = mock_adapter_class
            # Mock memory storage to prevent API calls
            mock_store.return_value = asyncio.Future()
            mock_store.return_value.set_result(None)

            # Import get_tool after patching
            from mcp_the_force.tools.registry import get_tool

            metadata = get_tool("chat_with_gemini25_flash")
            result = await executor.execute(
                metadata,
                instructions="Explain this code",
                output_format="markdown",
                context=[str(test_file)],
                temperature=0.5,
                session_id="gemini-test",
            )

            # Check that our mock was used
            assert mock_get_class.called
            assert mock_adapter_class.called

        # Verify adapter was called with correct params
        assert mock_gemini_adapter.generate.call_count >= 1
        call_args = mock_gemini_adapter.generate.call_args_list[0]

        # Check prompt was built
        prompt = call_args[1]["prompt"]
        assert "Explain this code" in prompt
        assert "markdown" in prompt
        assert "print('hello')" in prompt  # File content should be inlined

        # Check that params is a SimpleNamespace with correct values
        params = call_args[1]["params"]
        assert isinstance(params, SimpleNamespace)
        assert hasattr(params, "temperature")
        assert params.temperature == 0.5

        # Check result
        assert result == "Mock Gemini response"

    @pytest.mark.asyncio
    async def test_execute_openai_tool_with_session(
        self, executor, mock_openai_adapter
    ):
        """Test executing an OpenAI tool with session support."""
        mock_adapter_class = MagicMock(return_value=mock_openai_adapter)

        with (
            patch("mcp_the_force.tools.executor.get_adapter_class") as mock_get_class,
            patch(
                "mcp_the_force.memory.conversation.store_conversation_memory"
            ) as mock_store,
        ):
            mock_get_class.return_value = mock_adapter_class
            # Mock memory storage to prevent API calls
            mock_store.return_value = asyncio.Future()
            mock_store.return_value.set_result(None)

            # Mock session cache methods directly
            with (
                patch(
                    "mcp_the_force.unified_session_cache.UnifiedSessionCache.get_response_id",
                    new_callable=AsyncMock,
                    return_value="previous_response_id",
                ),
                patch(
                    "mcp_the_force.unified_session_cache.UnifiedSessionCache.set_response_id",
                    new_callable=AsyncMock,
                ),
                patch(
                    "mcp_the_force.unified_session_cache.UnifiedSessionCache.get_history",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
                patch(
                    "mcp_the_force.unified_session_cache.UnifiedSessionCache.set_history",
                    new_callable=AsyncMock,
                ),
            ):
                from mcp_the_force.tools.registry import get_tool

                metadata = get_tool("chat_with_o3")
                await executor.execute(
                    metadata,
                    instructions="Continue our discussion",
                    output_format="text",
                    context=[],
                    session_id="test-session",
                    reasoning_effort="high",
                )

        # Verify adapter was called with CallContext
        assert mock_openai_adapter.generate.called
        call_args = mock_openai_adapter.generate.call_args_list[0]
        ctx = call_args[1]["ctx"]
        assert isinstance(ctx, CallContext)
        assert ctx.session_id == "test-session"

    @pytest.mark.asyncio
    async def test_missing_required_parameter(self, executor):
        """Test that missing required parameter raises appropriate error."""
        with pytest.raises(fastmcp.exceptions.ToolError, match="Tool execution failed"):
            from mcp_the_force.tools.registry import get_tool

            metadata = get_tool("chat_with_gemini25_flash")
            await executor.execute(
                metadata,
                instructions="Test",
                # Missing output_format and context
                session_id="missing-param",
            )

    @pytest.mark.asyncio
    async def test_invalid_tool_name(self, executor):
        """Test that invalid tool name returns None."""
        # Test that get_tool returns None for invalid tools
        from mcp_the_force.tools.registry import get_tool

        metadata = get_tool("invalid_tool_name")
        assert metadata is None

        # Can't execute with None metadata
        if metadata is None:
            # This is the expected behavior
            pass

    @pytest.mark.asyncio
    async def test_adapter_error_handling(self, executor, mock_adapter):
        """Test that adapter errors are handled gracefully."""
        # Make adapter raise an exception
        mock_adapter.generate.side_effect = Exception("Adapter error")

        mock_adapter_class = MagicMock(return_value=mock_adapter)

        with patch("mcp_the_force.tools.executor.get_adapter_class") as mock_get_class:
            mock_get_class.return_value = mock_adapter_class

            from mcp_the_force.tools.registry import get_tool

            metadata = get_tool("chat_with_gemini25_flash")
            with pytest.raises(
                fastmcp.exceptions.ToolError, match="Failed to initialize adapter"
            ):
                await executor.execute(
                    metadata,
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="adapter-error",
                )

    @pytest.mark.asyncio
    async def test_local_service_tool(self, executor):
        """Test executing a local service tool (non-AI)."""
        # Test with search_project_history which is a LocalService tool
        from mcp_the_force.tools.registry import get_tool

        metadata = get_tool("search_project_history")
        assert metadata is not None

        # Mock the service to avoid actual database access
        with patch(
            "mcp_the_force.tools.search_history.SearchHistoryService.execute"
        ) as mock_execute:
            mock_execute.return_value = '{"results": [], "total": 0}'

            result = await executor.execute(
                metadata,
                query="test search",
                max_results=10,
            )

            # Verify service was called
            assert mock_execute.called
            assert result == '{"results": [], "total": 0}'
