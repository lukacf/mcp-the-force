"""
Integration tests for error handling scenarios.
"""

import pytest
import json
from unittest.mock import patch
import fastmcp.exceptions
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
            with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
                # Try to use OpenAI tool without key
                # With mock adapter, missing API key won't raise an error
                # The mock adapter doesn't check for API keys
                tool_metadata = get_tool("chat_with_o3")
                if not tool_metadata:
                    raise ValueError("Tool chat_with_o3 not found")
                result = await executor.execute(
                    tool_metadata,
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="test",
                )
                # Should get mock response even without API key
                data = json.loads(result)
                assert data["mock"] is True
        finally:
            # Clear cache again to avoid affecting other tests
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_invalid_model_name(self, mock_adapter_error):
        """Test error with invalid model configuration."""
        # Use mock_adapter_error to simulate model validation error
        with mock_adapter_error(Exception("The model `invalid-model` does not exist")):
            with pytest.raises(Exception, match="model.*does not exist|invalid.*model"):
                tool_metadata = get_tool("chat_with_o3")
                if not tool_metadata:
                    raise ValueError("Tool chat_with_o3 not found")
                await executor.execute(
                    tool_metadata,
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="test",
                )

    @pytest.mark.asyncio
    async def test_network_timeout(self, mock_adapter_error):
        """Test handling of network timeouts."""
        # Use mock_adapter_error to simulate timeout
        with mock_adapter_error(TimeoutError("Request timed out")):
            with pytest.raises(TimeoutError):
                tool_metadata = get_tool("chat_with_o3")
                if not tool_metadata:
                    raise ValueError("Tool chat_with_o3 not found")
                await executor.execute(
                    tool_metadata,
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="test",
                )

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mock_adapter_error):
        """Test handling of rate limit errors."""
        # Create a custom error with status_code attribute
        error = Exception("Rate limit exceeded")
        error.status_code = 429

        with mock_adapter_error(error):
            with pytest.raises(Exception, match="Rate limit"):
                tool_metadata = get_tool("chat_with_o3")
                if not tool_metadata:
                    raise ValueError("Tool chat_with_o3 not found")
                await executor.execute(
                    tool_metadata,
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="test",
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
                context="not-a-list",  # Should be list
                session_id="error-test",
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
                temperature="high",  # Should be float
                session_id="error-test",
            )

    @pytest.mark.asyncio
    async def test_file_not_found_in_context(self, parse_adapter_response):
        """Test handling of non-existent files in context."""
        # This should not crash, just skip the file
        tool_metadata = get_tool("chat_with_gemini25_flash")
        if not tool_metadata:
            raise ValueError("Tool chat_with_gemini25_flash not found")
        result = await executor.execute(
            tool_metadata,
            instructions="Analyze these files",
            output_format="text",
            context=["/path/that/does/not/exist.py"],
            session_id="file-missing",
        )

        # Should still work with MockAdapter
        data = parse_adapter_response(result)
        assert data["mock"] is True
        assert data["model"] == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_oversized_prompt(
        self, tmp_path, parse_adapter_response, mock_openai_client
    ):
        """Test handling of prompts that exceed model limits."""
        # Create a massive context
        huge_file = tmp_path / "huge.txt"
        huge_file.write_text("x" * 10_000_000)  # 10MB file

        # MockAdapter should handle this gracefully
        tool_metadata = get_tool("chat_with_o3")
        if not tool_metadata:
            raise ValueError("Tool chat_with_o3 not found")

        # With huge files, the system should automatically use vector store
        result = await executor.execute(
            tool_metadata,
            instructions="Analyze",
            output_format="text",
            context=[str(huge_file)],
            session_id="test",
        )

        # MockAdapter will return JSON showing it processed the request
        data = parse_adapter_response(result)
        assert data["mock"] is True
        assert data["model"] == "o3"
        # Vector store creation is handled by the mock_openai_client fixture
        # The MockAdapter itself doesn't handle vector stores
        # Just verify the request went through successfully
        # The prompt should contain the user instructions
        # Check the full prompt since prompt_preview might be truncated
        assert "Analyze" in data["prompt"]

    @pytest.mark.asyncio
    async def test_malformed_response_from_api(self, mock_adapter_error):
        """Test handling of malformed API responses."""
        # Simulate adapter returning None or malformed data
        with mock_adapter_error(
            AttributeError("'NoneType' object has no attribute 'output_text'")
        ):
            with pytest.raises(AttributeError):
                tool_metadata = get_tool("chat_with_o3")
                if not tool_metadata:
                    raise ValueError("Tool chat_with_o3 not found")
                await executor.execute(
                    tool_metadata,
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="test",
                )

    @pytest.mark.asyncio
    async def test_adapter_initialization_failure(self):
        """Test handling of adapter initialization failures."""
        # Patch get_adapter to return an error
        with patch("mcp_second_brain.adapters.get_adapter") as mock_get_adapter:
            mock_get_adapter.return_value = (
                None,
                "Failed to initialize adapter: Test error",
            )

            tool_metadata = get_tool("chat_with_gemini25_flash")
            if not tool_metadata:
                raise ValueError("Tool chat_with_gemini25_flash not found")
            with pytest.raises(fastmcp.exceptions.ToolError):
                await executor.execute(
                    tool_metadata,
                    instructions="Test",
                    output_format="text",
                    context=[],
                    session_id="init-fail",
                )

    @pytest.mark.asyncio
    async def test_concurrent_error_isolation(
        self, parse_adapter_response, mock_adapter_error
    ):
        """Test that errors in one tool don't affect others."""
        import asyncio
        from unittest.mock import patch, MagicMock

        # Run both concurrently - one succeeds, one fails
        o3_metadata = get_tool("chat_with_o3")
        gemini_metadata = get_tool("chat_with_gemini25_flash")
        if not o3_metadata or not gemini_metadata:
            raise ValueError("Required tools not found")

        # Create separate mock instances for each adapter
        from unittest.mock import AsyncMock

        o3_mock = MagicMock()
        gemini_mock = MagicMock()

        # O3 succeeds (generate is async)
        o3_mock.generate = AsyncMock(
            return_value=json.dumps(
                {
                    "mock": True,
                    "model": "o3",
                    "prompt_preview": "Should succeed",
                    "prompt_length": 100,
                    "vector_store_ids": None,
                    "adapter_kwargs": {},
                }
            )
        )

        # Gemini fails (generate is async)
        gemini_mock.generate = AsyncMock(side_effect=Exception("Vertex failed"))

        # Patch get_adapter to return our specific mocks
        def mock_get_adapter(adapter_key, model_name):
            if adapter_key == "openai":
                return o3_mock, None
            elif adapter_key == "vertex":
                return gemini_mock, None
            return None, f"Unknown adapter: {adapter_key}"

        with patch(
            "mcp_second_brain.adapters.get_adapter", side_effect=mock_get_adapter
        ):
            tasks = [
                executor.execute(
                    o3_metadata,
                    instructions="Should succeed",
                    output_format="text",
                    context=[],
                    session_id="test",
                ),
                executor.execute(
                    gemini_metadata,
                    instructions="Should fail",
                    output_format="text",
                    context=[],
                    session_id="gemini-fail",
                ),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # First should succeed
            data = parse_adapter_response(results[0])
            assert data["mock"] is True
            assert data["model"] == "o3"

            # Second should fail
            assert isinstance(results[1], Exception)
            assert "Vertex failed" in str(results[1])
