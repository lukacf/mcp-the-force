"""Unit tests for OpenAI adapter structured output conversion."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from mcp_second_brain.adapters.openai.adapter import OpenAIAdapter
from mcp_second_brain.adapters.openai.models import OpenAIRequest


class TestOpenAIStructuredOutput:
    """Test OpenAI adapter converts structured_output_schema to text.format."""

    def test_openai_request_accepts_structured_output_schema(self):
        """Test that OpenAIRequest model accepts structured_output_schema."""
        schema = {
            "type": "object",
            "properties": {"result": {"type": "boolean"}},
            "required": ["result"],
        }

        request = OpenAIRequest(
            model="gpt-4.1",
            messages=[{"role": "user", "content": "Is 2+2=4?"}],
            structured_output_schema=schema,
        )

        assert request.structured_output_schema == schema

    def test_to_api_format_converts_schema(self):
        """Test that to_api_format converts structured_output_schema to text.format."""
        schema = {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        }

        request = OpenAIRequest(
            model="gpt-4.1",
            messages=[{"role": "user", "content": "What is the capital of France?"}],
            structured_output_schema=schema,
        )

        api_format = request.to_api_format()

        # Should have text.format structure
        assert "text" in api_format
        assert "format" in api_format["text"]
        assert api_format["text"]["format"]["type"] == "json_schema"
        assert api_format["text"]["format"]["schema"] == schema
        assert api_format["text"]["format"].get("strict", True) is True

        # Original field should be removed
        assert "structured_output_schema" not in api_format

    @pytest.mark.asyncio
    async def test_adapter_passes_schema_to_api(self):
        """Test that adapter passes structured output schema to API."""
        schema = {
            "type": "object",
            "properties": {"result": {"type": "integer"}},
            "required": ["result"],
        }

        # Mock the settings to provide API key
        with patch("mcp_second_brain.config.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            adapter = OpenAIAdapter("gpt-4.1")

        # Mock the OpenAI client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.id = "resp_123"
        mock_response.status = "completed"
        mock_response.output_text = '{"result": 42}'
        mock_response.output = []

        mock_client.responses.create.return_value = mock_response
        mock_client.responses.retrieve.return_value = mock_response

        with patch(
            "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance",
            return_value=mock_client,
        ):
            await adapter.generate(
                prompt="What is the answer to life?", structured_output_schema=schema
            )

            # Check that the API was called with correct format
            create_call = mock_client.responses.create.call_args
            assert create_call is not None

            # Get the kwargs from the call
            api_params = create_call[1]

            # Should have text.format structure
            assert "text" in api_params
            assert api_params["text"]["format"]["type"] == "json_schema"
            assert api_params["text"]["format"]["schema"] == schema

    @pytest.mark.asyncio
    async def test_response_validation_success(self):
        """Test that valid JSON responses are validated and returned."""
        schema = {
            "type": "object",
            "properties": {"city": {"type": "string"}, "temp": {"type": "number"}},
            "required": ["city", "temp"],
        }

        # Mock the settings to provide API key
        with patch("mcp_second_brain.config.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            adapter = OpenAIAdapter("gpt-4.1")

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.id = "resp_123"
        mock_response.status = "completed"
        mock_response.output_text = '{"city": "Paris", "temp": 22.5}'
        mock_response.output = []

        mock_client.responses.create.return_value = mock_response

        with patch(
            "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance",
            return_value=mock_client,
        ):
            result = await adapter.generate(
                prompt="Weather in Paris?", structured_output_schema=schema
            )

            # Should return the validated content
            assert result["content"] == '{"city": "Paris", "temp": 22.5}'

    @pytest.mark.asyncio
    async def test_response_validation_skipped(self):
        """Test that validation is skipped and responses are returned as-is."""
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }

        # Mock the settings to provide API key
        with patch("mcp_second_brain.config.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            adapter = OpenAIAdapter("gpt-4.1")

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.id = "resp_123"
        mock_response.status = "completed"
        # Invalid: count is string instead of integer
        mock_response.output_text = '{"count": "not-a-number"}'
        mock_response.output = []

        mock_client.responses.create.return_value = mock_response

        with patch(
            "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance",
            return_value=mock_client,
        ):
            # Should return response as-is without validation
            result = await adapter.generate(
                prompt="Count something", structured_output_schema=schema
            )
            assert result["content"] == '{"count": "not-a-number"}'

    @pytest.mark.asyncio
    async def test_non_json_response_returned_as_is(self):
        """Test that non-JSON responses are returned as-is without validation."""
        schema = {"type": "object"}

        # Mock the settings to provide API key
        with patch("mcp_second_brain.config.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            adapter = OpenAIAdapter("gpt-4.1")

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.id = "resp_123"
        mock_response.status = "completed"
        # Not valid JSON
        mock_response.output_text = "This is not JSON"
        mock_response.output = []

        mock_client.responses.create.return_value = mock_response

        with patch(
            "mcp_second_brain.adapters.openai.client.OpenAIClientFactory.get_instance",
            return_value=mock_client,
        ):
            # Should return response as-is without validation
            result = await adapter.generate(
                prompt="Return text instead of JSON",
                structured_output_schema=schema,
            )
            assert result["content"] == "This is not JSON"
