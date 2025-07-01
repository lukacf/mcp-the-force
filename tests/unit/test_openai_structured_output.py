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
            adapter = OpenAIAdapter("gpt-4.1")

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
            adapter = OpenAIAdapter("gpt-4.1")

            result = await adapter.generate(
                prompt="Weather in Paris?", structured_output_schema=schema
            )

            # Should return the validated content
            assert result["content"] == '{"city": "Paris", "temp": 22.5}'

    @pytest.mark.asyncio
    async def test_response_validation_failure(self):
        """Test that invalid JSON responses raise validation errors."""
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }

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
            adapter = OpenAIAdapter("gpt-4.1")

            with pytest.raises(Exception, match="Structured output validation failed"):
                await adapter.generate(
                    prompt="Count something", structured_output_schema=schema
                )

    @pytest.mark.asyncio
    async def test_non_json_response_fails(self):
        """Test that non-JSON responses fail validation."""
        schema = {"type": "object"}

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
            adapter = OpenAIAdapter("gpt-4.1")

            with pytest.raises(Exception, match="Structured output validation failed"):
                await adapter.generate(
                    prompt="Return text instead of JSON",
                    structured_output_schema=schema,
                )
