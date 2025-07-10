"""Integration tests for ToolExecutor session handling across different adapters."""

import pytest
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_second_brain.tools.executor import ToolExecutor
from mcp_second_brain.tools.registry import ToolMetadata
from mcp_second_brain.tools.definitions import ChatWithGrok4
from mcp_second_brain import session_cache as session_cache_module
from mcp_second_brain import gemini_session_cache as gemini_session_cache_module
from mcp_second_brain import grok_session_cache as grok_session_cache_module


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp:
        db_path = tmp.name
    yield db_path
    try:
        os.unlink(db_path)
    except FileNotFoundError:
        pass


@pytest.fixture
def mock_tool_metadata():
    """Create mock tool metadata for testing."""
    metadata = MagicMock(spec=ToolMetadata)
    metadata.id = "chat_with_grok4"
    metadata.spec_class = ChatWithGrok4
    metadata.model_config = {
        "adapter_class": "xai",
        "model_name": "grok-4",
        "timeout": 300,
    }
    return metadata


@pytest.fixture
def mock_openai_tool_metadata():
    """Create mock OpenAI tool metadata for testing."""
    metadata = MagicMock(spec=ToolMetadata)
    metadata.id = "chat_with_o3"
    metadata.spec_class = MagicMock()  # Mock spec class
    metadata.model_config = {
        "adapter_class": "openai",
        "model_name": "o3",
        "timeout": 300,
    }
    return metadata


@pytest.fixture
def mock_vertex_tool_metadata():
    """Create mock Vertex tool metadata for testing."""
    metadata = MagicMock(spec=ToolMetadata)
    metadata.id = "chat_with_gemini25_pro"
    metadata.spec_class = MagicMock()  # Mock spec class
    metadata.model_config = {
        "adapter_class": "vertex",
        "model_name": "gemini-2.5-pro",
        "timeout": 300,
    }
    return metadata


@pytest.fixture
def tool_executor():
    """Create ToolExecutor instance for testing."""
    return ToolExecutor(strict_mode=False)


class TestToolExecutorSessionHandling:
    """Test ToolExecutor session handling for different adapter types."""

    @pytest.mark.asyncio
    async def test_grok_session_loading_and_passing(
        self, tool_executor, mock_tool_metadata
    ):
        """Test that Grok sessions are loaded and passed to the adapter."""
        session_id = "test-grok-session"

        # Mock session history
        mock_history = [
            {"role": "user", "content": "Previous message"},
            {"role": "assistant", "content": "Previous response"},
        ]

        with patch.object(
            grok_session_cache_module.grok_session_cache,
            "get_history",
            return_value=mock_history,
        ) as mock_get_history, patch(
            "mcp_second_brain.adapters.get_adapter"
        ) as mock_get_adapter, patch.object(
            tool_executor.validator, "validate"
        ) as mock_validate, patch.object(
            tool_executor.router, "route"
        ) as mock_route, patch(
            "mcp_second_brain.config.get_settings"
        ) as mock_settings, patch(
            "mcp_second_brain.adapters.model_registry.get_model_context_window",
            return_value=256000,
        ), patch(
            "mcp_second_brain.utils.context_builder.build_context_with_stable_list"
        ) as mock_build_context:
            # Setup mocks
            mock_adapter = AsyncMock()
            mock_adapter.generate = AsyncMock(
                return_value="Grok response with session context"
            )
            mock_get_adapter.return_value = (mock_adapter, None)

            mock_validate.return_value = {
                "instructions": "Test instructions",
                "output_format": "Text format",
                "context": [],
                "session_id": session_id,
            }

            mock_route.return_value = {
                "prompt": {
                    "instructions": "Test instructions",
                    "output_format": "Text format",
                    "context": [],
                    "messages": [],
                },
                "adapter": {"temperature": 1.0},
                "session": {"session_id": session_id},
                "vector_store": [],
                "vector_store_ids": [],
                "structured_output": {},
            }

            mock_settings.return_value.mcp.context_percentage = 0.85
            mock_settings.return_value.memory_enabled = False

            mock_build_context.return_value = ([], [])

            # Execute tool
            result = await tool_executor.execute(
                metadata=mock_tool_metadata,
                instructions="Test instructions",
                output_format="Text format",
                context=[],
                session_id=session_id,
            )

            # Verify session was loaded
            mock_get_history.assert_called_once_with(session_id)

            # Verify adapter was called with messages
            mock_adapter.generate.assert_called_once()
            call_args = mock_adapter.generate.call_args

            # Should have messages parameter with session history
            assert "messages" in call_args.kwargs
            assert call_args.kwargs["messages"] == mock_history

            assert result == "Grok response with session context"

    @pytest.mark.asyncio
    async def test_openai_session_handling(
        self, tool_executor, mock_openai_tool_metadata
    ):
        """Test OpenAI session handling with response IDs."""
        session_id = "test-openai-session"
        mock_response_id = "resp_12345"

        with patch.object(
            session_cache_module.session_cache,
            "get_response_id",
            return_value=mock_response_id,
        ) as mock_get_response_id, patch.object(
            session_cache_module.session_cache, "set_response_id"
        ) as mock_set_response_id, patch(
            "mcp_second_brain.adapters.get_adapter"
        ) as mock_get_adapter, patch.object(
            tool_executor.validator, "validate"
        ) as mock_validate, patch.object(
            tool_executor.router, "route"
        ) as mock_route, patch(
            "mcp_second_brain.config.get_settings"
        ) as mock_settings, patch(
            "mcp_second_brain.adapters.model_registry.get_model_context_window",
            return_value=200000,
        ), patch(
            "mcp_second_brain.utils.context_builder.build_context_with_stable_list"
        ) as mock_build_context:
            # Setup mocks
            mock_adapter = AsyncMock()
            mock_adapter.generate = AsyncMock(
                return_value={
                    "content": "OpenAI response",
                    "response_id": "new_resp_67890",
                }
            )
            mock_get_adapter.return_value = (mock_adapter, None)

            mock_validate.return_value = {
                "instructions": "Test instructions",
                "output_format": "Text format",
                "context": [],
                "session_id": session_id,
            }

            mock_route.return_value = {
                "prompt": {
                    "instructions": "Test instructions",
                    "output_format": "Text format",
                    "context": [],
                    "messages": [],
                },
                "adapter": {"temperature": 1.0},
                "session": {"session_id": session_id},
                "vector_store": [],
                "vector_store_ids": [],
                "structured_output": {},
            }

            mock_settings.return_value.mcp.context_percentage = 0.85
            mock_settings.return_value.memory_enabled = False

            mock_build_context.return_value = ([], [])

            # Execute tool
            result = await tool_executor.execute(
                metadata=mock_openai_tool_metadata,
                instructions="Test instructions",
                output_format="Text format",
                context=[],
                session_id=session_id,
            )

            # Verify previous response ID was retrieved
            mock_get_response_id.assert_called_once_with(session_id)

            # Verify adapter was called with previous_response_id
            mock_adapter.generate.assert_called_once()
            call_args = mock_adapter.generate.call_args
            assert "previous_response_id" in call_args.kwargs
            assert call_args.kwargs["previous_response_id"] == mock_response_id

            # Verify new response ID was stored
            mock_set_response_id.assert_called_once_with(session_id, "new_resp_67890")

            assert result == "OpenAI response"

    @pytest.mark.asyncio
    async def test_vertex_session_handling(
        self, tool_executor, mock_vertex_tool_metadata
    ):
        """Test Vertex (Gemini) session handling with history."""
        session_id = "test-vertex-session"

        # Mock Gemini history (Content objects)
        from google.genai import types

        mock_gemini_history = [
            types.Content(
                role="user", parts=[types.Part.from_text("Previous question")]
            ),
            types.Content(
                role="assistant", parts=[types.Part.from_text("Previous answer")]
            ),
        ]

        with patch.object(
            gemini_session_cache_module.gemini_session_cache,
            "get_history",
            return_value=mock_gemini_history,
        ) as mock_get_history, patch(
            "mcp_second_brain.adapters.get_adapter"
        ) as mock_get_adapter, patch.object(
            tool_executor.validator, "validate"
        ) as mock_validate, patch.object(
            tool_executor.router, "route"
        ) as mock_route, patch(
            "mcp_second_brain.config.get_settings"
        ) as mock_settings, patch(
            "mcp_second_brain.adapters.model_registry.get_model_context_window",
            return_value=2000000,
        ), patch(
            "mcp_second_brain.utils.context_builder.build_context_with_stable_list"
        ) as mock_build_context:
            # Setup mocks
            mock_adapter = AsyncMock()
            mock_adapter.generate = AsyncMock(
                return_value="Gemini response with history"
            )
            mock_get_adapter.return_value = (mock_adapter, None)

            mock_validate.return_value = {
                "instructions": "Test instructions",
                "output_format": "Text format",
                "context": [],
                "session_id": session_id,
            }

            mock_route.return_value = {
                "prompt": {
                    "instructions": "Test instructions",
                    "output_format": "Text format",
                    "context": [],
                    "messages": [],
                },
                "adapter": {"temperature": 1.0},
                "session": {"session_id": session_id},
                "vector_store": [],
                "vector_store_ids": [],
                "structured_output": {},
            }

            mock_settings.return_value.mcp.context_percentage = 0.85
            mock_settings.return_value.memory_enabled = False

            mock_build_context.return_value = ([], [])

            # Execute tool
            result = await tool_executor.execute(
                metadata=mock_vertex_tool_metadata,
                instructions="Test instructions",
                output_format="Text format",
                context=[],
                session_id=session_id,
            )

            # Verify session history was loaded
            mock_get_history.assert_called_once_with(session_id)

            # Verify adapter was called with messages including history
            mock_adapter.generate.assert_called_once()
            call_args = mock_adapter.generate.call_args

            # Should have messages with Gemini history + new user message
            assert "messages" in call_args.kwargs
            messages = call_args.kwargs["messages"]

            # Should be converted to dict format for the adapter
            assert len(messages) >= 3  # history + new user message
            assert messages[-1]["content"] == "Test instructions"  # New user message

            assert result == "Gemini response with history"

    @pytest.mark.asyncio
    async def test_session_isolation_between_adapters(self, tool_executor):
        """Test that different adapter types maintain separate session states."""
        session_id = "shared-session-id"

        # Mock histories for different adapters
        mock_grok_history = [{"role": "user", "content": "Grok conversation"}]
        mock_openai_response_id = "openai_resp_123"

        from google.genai import types

        mock_gemini_history = [
            types.Content(
                role="user", parts=[types.Part.from_text("Gemini conversation")]
            )
        ]

        with patch.object(
            grok_session_cache_module.grok_session_cache,
            "get_history",
            return_value=mock_grok_history,
        ), patch.object(
            session_cache_module.session_cache,
            "get_response_id",
            return_value=mock_openai_response_id,
        ), patch.object(
            gemini_session_cache_module.gemini_session_cache,
            "get_history",
            return_value=mock_gemini_history,
        ), patch(
            "mcp_second_brain.adapters.get_adapter"
        ) as mock_get_adapter, patch.object(
            tool_executor.validator, "validate"
        ) as mock_validate, patch.object(
            tool_executor.router, "route"
        ) as mock_route, patch(
            "mcp_second_brain.config.get_settings"
        ) as mock_settings, patch(
            "mcp_second_brain.adapters.model_registry.get_model_context_window",
            return_value=256000,
        ), patch(
            "mcp_second_brain.utils.context_builder.build_context_with_stable_list"
        ) as mock_build_context:
            # Common mock setup
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = (mock_adapter, None)
            mock_settings.return_value.mcp.context_percentage = 0.85
            mock_settings.return_value.memory_enabled = False
            mock_build_context.return_value = ([], [])

            # Test Grok adapter
            mock_tool_metadata.model_config["adapter_class"] = "xai"
            mock_validate.return_value = {
                "instructions": "Test",
                "output_format": "Text",
                "context": [],
                "session_id": session_id,
            }
            mock_route.return_value = {
                "prompt": {
                    "instructions": "Test",
                    "output_format": "Text",
                    "context": [],
                    "messages": [],
                },
                "adapter": {"temperature": 1.0},
                "session": {"session_id": session_id},
                "vector_store": [],
                "vector_store_ids": [],
                "structured_output": {},
            }

            mock_adapter.generate = AsyncMock(return_value="Grok response")
            await tool_executor.execute(mock_tool_metadata, session_id=session_id)

            # Verify Grok messages were passed
            grok_call_args = mock_adapter.generate.call_args
            assert "messages" in grok_call_args.kwargs
            assert grok_call_args.kwargs["messages"] == mock_grok_history

            # Test OpenAI adapter
            mock_openai_tool_metadata.model_config["adapter_class"] = "openai"
            mock_adapter.generate = AsyncMock(
                return_value={"content": "OpenAI response", "response_id": "new_123"}
            )
            await tool_executor.execute(
                mock_openai_tool_metadata, session_id=session_id
            )

            # Verify OpenAI response ID was passed
            openai_call_args = mock_adapter.generate.call_args
            assert "previous_response_id" in openai_call_args.kwargs
            assert (
                openai_call_args.kwargs["previous_response_id"]
                == mock_openai_response_id
            )

            # Test Vertex adapter
            mock_vertex_tool_metadata.model_config["adapter_class"] = "vertex"
            mock_adapter.generate = AsyncMock(return_value="Gemini response")
            await tool_executor.execute(
                mock_vertex_tool_metadata, session_id=session_id
            )

            # Verify Gemini history was passed (converted to dict format)
            vertex_call_args = mock_adapter.generate.call_args
            assert "messages" in vertex_call_args.kwargs
            vertex_messages = vertex_call_args.kwargs["messages"]
            assert len(vertex_messages) >= 2  # history + new message

    @pytest.mark.asyncio
    async def test_session_handling_without_session_id(
        self, tool_executor, mock_tool_metadata
    ):
        """Test that tools work correctly without session IDs."""
        with patch(
            "mcp_second_brain.adapters.get_adapter"
        ) as mock_get_adapter, patch.object(
            tool_executor.validator, "validate"
        ) as mock_validate, patch.object(
            tool_executor.router, "route"
        ) as mock_route, patch(
            "mcp_second_brain.config.get_settings"
        ) as mock_settings, patch(
            "mcp_second_brain.adapters.model_registry.get_model_context_window",
            return_value=256000,
        ), patch(
            "mcp_second_brain.utils.context_builder.build_context_with_stable_list"
        ) as mock_build_context:
            # Setup mocks
            mock_adapter = AsyncMock()
            mock_adapter.generate = AsyncMock(return_value="Response without session")
            mock_get_adapter.return_value = (mock_adapter, None)

            mock_validate.return_value = {
                "instructions": "Test instructions",
                "output_format": "Text format",
                "context": [],
                # No session_id
            }

            mock_route.return_value = {
                "prompt": {
                    "instructions": "Test instructions",
                    "output_format": "Text format",
                    "context": [],
                    "messages": [],
                },
                "adapter": {"temperature": 1.0},
                "session": {},  # Empty session params
                "vector_store": [],
                "vector_store_ids": [],
                "structured_output": {},
            }

            mock_settings.return_value.mcp.context_percentage = 0.85
            mock_settings.return_value.memory_enabled = False

            mock_build_context.return_value = ([], [])

            # Execute tool without session_id
            result = await tool_executor.execute(
                metadata=mock_tool_metadata,
                instructions="Test instructions",
                output_format="Text format",
                context=[],
                # No session_id parameter
            )

            # Verify adapter was called without session-specific parameters
            mock_adapter.generate.assert_called_once()
            call_args = mock_adapter.generate.call_args

            # Should not have messages, previous_response_id, etc.
            assert (
                "messages" not in call_args.kwargs
                or call_args.kwargs.get("messages") is None
            )
            assert "previous_response_id" not in call_args.kwargs

            assert result == "Response without session"

    @pytest.mark.asyncio
    async def test_error_handling_in_session_operations(
        self, tool_executor, mock_tool_metadata
    ):
        """Test error handling when session operations fail."""
        session_id = "error-session"

        with patch.object(
            grok_session_cache_module.grok_session_cache,
            "get_history",
            side_effect=Exception("Session cache error"),
        ) as mock_get_history, patch(
            "mcp_second_brain.adapters.get_adapter"
        ) as mock_get_adapter, patch.object(
            tool_executor.validator, "validate"
        ) as mock_validate, patch.object(
            tool_executor.router, "route"
        ) as mock_route, patch(
            "mcp_second_brain.config.get_settings"
        ) as mock_settings, patch(
            "mcp_second_brain.adapters.model_registry.get_model_context_window",
            return_value=256000,
        ), patch(
            "mcp_second_brain.utils.context_builder.build_context_with_stable_list"
        ) as mock_build_context:
            # Setup mocks
            mock_adapter = AsyncMock()
            mock_adapter.generate = AsyncMock(
                return_value="Response despite session error"
            )
            mock_get_adapter.return_value = (mock_adapter, None)

            mock_validate.return_value = {
                "instructions": "Test instructions",
                "output_format": "Text format",
                "context": [],
                "session_id": session_id,
            }

            mock_route.return_value = {
                "prompt": {
                    "instructions": "Test instructions",
                    "output_format": "Text format",
                    "context": [],
                    "messages": [],
                },
                "adapter": {"temperature": 1.0},
                "session": {"session_id": session_id},
                "vector_store": [],
                "vector_store_ids": [],
                "structured_output": {},
            }

            mock_settings.return_value.mcp.context_percentage = 0.85
            mock_settings.return_value.memory_enabled = False

            mock_build_context.return_value = ([], [])

            # Execute tool - should handle session error gracefully
            with pytest.raises(Exception, match="Session cache error"):
                await tool_executor.execute(
                    metadata=mock_tool_metadata,
                    instructions="Test instructions",
                    output_format="Text format",
                    context=[],
                    session_id=session_id,
                )

            # Verify session get was attempted
            mock_get_history.assert_called_once_with(session_id)
