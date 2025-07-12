"""Test Vertex adapter thread safety and async behavior."""

import pytest
import asyncio
import threading
from unittest.mock import Mock, patch, AsyncMock
from google.genai import types
from mcp_second_brain.adapters.vertex.adapter import VertexAdapter, get_client
import mcp_second_brain.adapters.vertex.adapter as vertex_module


def create_mock_response(with_function_call=False, text="Test response"):
    """Create a mock response object."""
    mock_part = Mock()
    mock_part.text = text
    mock_part.function_call = (
        Mock(name="search_project_memory", args={"query": "test"})
        if with_function_call
        else None
    )

    mock_content = Mock()
    mock_content.parts = [mock_part]

    mock_candidate = Mock()
    mock_candidate.content = mock_content

    mock_response = Mock()
    mock_response.candidates = [mock_candidate]

    return mock_response


class TestVertexThreadSafety:
    """Test Vertex adapter thread safety and async behavior."""

    @pytest.mark.asyncio
    async def test_vertex_runs_in_thread(self, monkeypatch):
        """Verify Vertex calls run in thread pool."""
        main_thread_id = threading.get_ident()
        call_thread_id = None
        called_in_thread = False

        def mock_generate(*args, **kwargs):
            nonlocal call_thread_id, called_in_thread
            call_thread_id = threading.get_ident()
            # Should be in different thread when called via asyncio.to_thread
            called_in_thread = call_thread_id != main_thread_id
            return create_mock_response()

        mock_client = Mock()
        mock_client.models.generate_content = mock_generate

        # Track calls to asyncio.to_thread
        to_thread_called = False
        original_to_thread = asyncio.to_thread

        async def track_to_thread(func, *args, **kwargs):
            nonlocal to_thread_called
            to_thread_called = True
            # Actually run in thread to test the real behavior
            return await original_to_thread(func, *args, **kwargs)

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.genai.Client",
            return_value=mock_client,
        ):
            # Clear the cached singleton client
            vertex_module._client = None

            # Patch asyncio.to_thread correctly
            with patch.object(
                vertex_module.asyncio, "to_thread", side_effect=track_to_thread
            ):
                monkeypatch.setenv("VERTEX_PROJECT", "test-project")
                monkeypatch.setenv("VERTEX_LOCATION", "us-central1")

                # Clear settings cache
                from mcp_second_brain.config import get_settings

                get_settings.cache_clear()

                adapter = VertexAdapter("gemini-2.5-pro")

                await adapter.generate("test prompt")

                # Verify asyncio.to_thread was called
                assert to_thread_called, "asyncio.to_thread should be called"
                assert call_thread_id is not None, (
                    "generate_content should have been called"
                )
                assert called_in_thread, (
                    "generate_content should be called in a different thread"
                )

    @pytest.mark.asyncio
    async def test_cancellation_propagates(self, monkeypatch):
        """Test that cancellation properly propagates."""

        async def slow_generate(*args, **kwargs):
            await asyncio.sleep(10)  # Simulate slow operation
            return create_mock_response()

        mock_client = Mock()

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.genai.Client",
            return_value=mock_client,
        ):
            # Clear the cached singleton client
            vertex_module._client = None

            with patch.object(
                vertex_module.asyncio, "to_thread", side_effect=slow_generate
            ):
                monkeypatch.setenv("VERTEX_PROJECT", "test-project")
                monkeypatch.setenv("VERTEX_LOCATION", "us-central1")

                adapter = VertexAdapter("gemini-2.5-pro")

                # Create and cancel the task
                task = asyncio.create_task(adapter.generate("test"))
                await asyncio.sleep(0.1)
                task.cancel()

                with pytest.raises(asyncio.CancelledError):
                    await task

    @pytest.mark.asyncio
    async def test_function_call_limit_enforced(self, monkeypatch):
        """Test that function calls are limited."""
        call_count = 0

        def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Always return a function call
            return create_mock_response(with_function_call=True)

        mock_client = Mock()
        mock_client.models.generate_content = mock_generate

        mock_search = Mock()
        mock_search.generate = AsyncMock(return_value="search results")

        # Patch asyncio.to_thread to run synchronously for testing
        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.genai.Client",
            return_value=mock_client,
        ):
            # Clear the cached singleton client
            vertex_module._client = None

            with patch.object(
                vertex_module.asyncio, "to_thread", side_effect=mock_to_thread
            ):
                with patch(
                    "mcp_second_brain.tools.search_memory.SearchMemoryAdapter",
                    return_value=mock_search,
                ):
                    monkeypatch.setenv("VERTEX_PROJECT", "test-project")
                    monkeypatch.setenv("VERTEX_LOCATION", "us-central1")
                    monkeypatch.setenv("VERTEX__MAX_FUNCTION_CALLS", "3")

                    from mcp_second_brain.config import get_settings

                    get_settings.cache_clear()

                    adapter = VertexAdapter("gemini-2.5-pro")

                    # Create initial response with function call
                    initial_response = create_mock_response(with_function_call=True)

                    # Create initial conversation context
                    contents = [
                        types.Content(
                            role="user", parts=[types.Part(text="Search for test")]
                        )
                    ]

                    # Call the handler
                    result, _ = await adapter._handle_function_calls(
                        initial_response, contents, types.GenerateContentConfig()
                    )

                    # Should hit the limit
                    assert call_count == 3  # 3 follow-up calls after initial
                    assert "TooManyFunctionCalls" in result
                    assert "Exceeded 3 function call rounds" in result

    @pytest.mark.asyncio
    async def test_max_output_tokens_from_config(self, monkeypatch):
        """Test that max_output_tokens is read from config."""
        mock_client = Mock()
        generate_content_config = None

        def capture_config(*args, **kwargs):
            nonlocal generate_content_config
            if "config" in kwargs:
                generate_content_config = kwargs["config"]
            return create_mock_response()

        mock_client.models.generate_content = capture_config

        # Patch asyncio.to_thread to run synchronously for testing
        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.genai.Client",
            return_value=mock_client,
        ):
            # Clear the cached singleton client
            vertex_module._client = None

            with patch.object(
                vertex_module.asyncio, "to_thread", side_effect=mock_to_thread
            ):
                monkeypatch.setenv("VERTEX_PROJECT", "test-project")
                monkeypatch.setenv("VERTEX_LOCATION", "us-central1")
                monkeypatch.setenv("VERTEX__MAX_OUTPUT_TOKENS", "4096")

                from mcp_second_brain.config import get_settings

                get_settings.cache_clear()

                adapter = VertexAdapter("gemini-2.5-pro")
                await adapter.generate("test")

                assert generate_content_config is not None
                assert generate_content_config.max_output_tokens == 4096

    @pytest.mark.asyncio
    async def test_function_call_error_handling(self, monkeypatch):
        """Test that function call errors are handled gracefully."""
        # The handler already has the first response with function call,
        # so mock should only return the final response
        responses = [create_mock_response(text="Final response")]
        call_idx = 0

        def mock_generate(*args, **kwargs):
            nonlocal call_idx
            resp = responses[min(call_idx, len(responses) - 1)]
            call_idx += 1
            return resp

        mock_client = Mock()
        mock_client.models.generate_content = Mock(side_effect=mock_generate)

        mock_search = Mock()
        mock_search.generate = AsyncMock(side_effect=Exception("Database error"))

        # Patch asyncio.to_thread to run synchronously for testing
        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.genai.Client",
            return_value=mock_client,
        ):
            # Clear the cached singleton client
            vertex_module._client = None

            with patch.object(
                vertex_module.asyncio, "to_thread", side_effect=mock_to_thread
            ):
                with patch(
                    "mcp_second_brain.tools.search_memory.SearchMemoryAdapter",
                    return_value=mock_search,
                ):
                    monkeypatch.setenv("VERTEX_PROJECT", "test-project")
                    monkeypatch.setenv("VERTEX_LOCATION", "us-central1")

                    adapter = VertexAdapter("gemini-2.5-pro")

                    # Create initial response with function call
                    initial_response = create_mock_response(with_function_call=True)

                    # Call the handler
                    result, _ = await adapter._handle_function_calls(
                        initial_response, [], types.GenerateContentConfig()
                    )

                    # Should return the final text despite the error
                    assert result == "Final response"

                    # Verify that generate_content was called to continue after error
                    assert mock_client.models.generate_content.call_count == 1

    def test_client_singleton_thread_safety(self):
        """Test get_client is thread-safe."""
        # Clear the client
        vertex_module._client = None

        clients = []

        def get_client_thread():
            clients.append(get_client())

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.genai.Client"
        ) as mock_client_class:
            mock_client_class.return_value = Mock()

            with patch("mcp_second_brain.config.get_settings") as mock_settings:
                mock_settings.return_value.vertex_project = "test-project"
                mock_settings.return_value.vertex_location = "us-central1"

                # Create multiple threads
                threads = []
                for _ in range(10):
                    t = threading.Thread(target=get_client_thread)
                    threads.append(t)
                    t.start()

                # Wait for all threads
                for t in threads:
                    t.join()

                # Should only create one client
                assert mock_client_class.call_count == 1
                # All should be the same instance
                assert all(c is clients[0] for c in clients)
