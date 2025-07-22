"""Unit tests for Gemini/Vertex adapter structured output conversion."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

from mcp_second_brain.adapters.vertex.adapter import VertexAdapter


class TestGeminiStructuredOutput:
    """Test Gemini adapter converts structured_output_schema to response_schema."""

    @pytest.mark.asyncio
    async def test_adapter_accepts_structured_output_schema(self):
        """Test that VertexAdapter accepts structured_output_schema parameter."""
        adapter = VertexAdapter("gemini-2.5-flash")

        schema = {
            "type": "object",
            "properties": {"result": {"type": "boolean"}},
            "required": ["result"],
        }

        # Mock the Gemini client
        mock_client = MagicMock()
        # Set up aio structure
        mock_client.aio = MagicMock()
        mock_client.aio.models = MagicMock()
        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [MagicMock()]
        mock_response.candidates[0].content.parts[0].text = '{"result": true}'
        mock_response.candidates[0].content.parts[0].function_call = None
        # Mock response.text property to return JSON string
        mock_response.text = '{"result": true}'

        # Create async mock for aio client
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.get_client",
            return_value=mock_client,
        ):
            with patch.object(
                adapter, "_generate_async", new_callable=AsyncMock
            ) as mock_gen:
                mock_gen.return_value = mock_response
                # Should accept structured_output_schema parameter
                result = await adapter.generate(
                    prompt="Is 2+2=4?", structured_output_schema=schema
                )

                assert result == '{"result": true}'

    @pytest.mark.asyncio
    async def test_response_schema_passed_to_config(self):
        """Test that structured_output_schema is passed as response_schema to Gemini."""
        adapter = VertexAdapter("gemini-2.5-pro")

        schema = {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "temperature": {"type": "number"},
            },
            "required": ["city", "temperature"],
        }

        mock_client = MagicMock()
        # Set up aio structure
        mock_client.aio = MagicMock()
        mock_client.aio.models = MagicMock()
        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [MagicMock()]
        mock_response.candidates[0].content.parts[
            0
        ].text = '{"city": "London", "temperature": 18.5}'
        mock_response.candidates[0].content.parts[0].function_call = None
        # Mock response.text property to return JSON string
        mock_response.text = '{"city": "London", "temperature": 18.5}'

        # Create async mock for aio client
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.get_client",
            return_value=mock_client,
        ):
            await adapter.generate(
                prompt="Weather in London?", structured_output_schema=schema
            )

            # Check that generate_content was called with response_schema
            call_args = mock_client.aio.models.generate_content.call_args
            assert call_args is not None

            # Extract config from call
            config = call_args[1]["config"]

            # Should have response_schema set
            assert (
                hasattr(config, "response_schema")
                or "response_schema" in config.__dict__
            )
            # The schema should be converted to types.Schema
            if hasattr(config, "response_schema"):
                response_schema = config.response_schema
            else:
                response_schema = config.__dict__["response_schema"]

            # Check it's a Schema object with correct structure
            assert hasattr(response_schema, "type")
            assert hasattr(response_schema, "properties")
            assert hasattr(response_schema, "required")

    @pytest.mark.asyncio
    async def test_system_instruction_added_for_json(self):
        """Test that system instruction is added when using structured output."""
        adapter = VertexAdapter("gemini-2.5-flash")

        schema = {"type": "object"}

        mock_client = MagicMock()
        # Set up aio structure
        mock_client.aio = MagicMock()
        mock_client.aio.models = MagicMock()
        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [MagicMock()]
        mock_response.candidates[0].content.parts[0].text = "{}"
        mock_response.candidates[0].content.parts[0].function_call = None
        # Mock response.text property to return JSON string
        mock_response.text = "{}"

        # Create async mock for aio client
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.get_client",
            return_value=mock_client,
        ):
            await adapter.generate(
                prompt="Return empty object", structured_output_schema=schema
            )

            # Check that system instruction mentions JSON
            call_args = mock_client.aio.models.generate_content.call_args
            config = call_args[1]["config"]

            assert (
                hasattr(config, "system_instruction")
                or "system_instruction" in config.__dict__
            )
            if hasattr(config, "system_instruction"):
                assert "JSON" in config.system_instruction
            else:
                assert "JSON" in config.__dict__.get("system_instruction", "")

    @pytest.mark.asyncio
    async def test_response_validation_success(self):
        """Test that valid JSON responses are validated and returned."""
        adapter = VertexAdapter("gemini-2.5-pro")

        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }

        mock_client = MagicMock()
        # Set up aio structure
        mock_client.aio = MagicMock()
        mock_client.aio.models = MagicMock()
        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [MagicMock()]
        mock_response.candidates[0].content.parts[0].text = '{"count": 42}'
        mock_response.candidates[0].content.parts[0].function_call = None
        # Mock response.text property to return JSON string
        mock_response.text = '{"count": 42}'

        # Create async mock for aio client
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.get_client",
            return_value=mock_client,
        ):
            result = await adapter.generate(
                prompt="Count to 42", structured_output_schema=schema
            )

            # Should return the validated JSON
            assert result == '{"count": 42}'
            # Verify it's valid JSON
            parsed = json.loads(result)
            assert parsed["count"] == 42

    @pytest.mark.asyncio
    async def test_response_validation_enforced(self):
        """Test that validation is enforced and raises errors for invalid responses."""
        adapter = VertexAdapter("gemini-2.5-flash")

        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer"}},
            "required": ["age"],
        }

        mock_client = MagicMock()
        # Set up aio structure
        mock_client.aio = MagicMock()
        mock_client.aio.models = MagicMock()
        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [MagicMock()]
        # Invalid JSON - should raise validation error
        mock_response.candidates[0].content.parts[0].text = '{"age": "not_a_number"}'
        mock_response.candidates[0].content.parts[0].function_call = None
        # Mock response.text property to return JSON string
        mock_response.text = '{"age": "not_a_number"}'

        # Create async mock for aio client
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.get_client",
            return_value=mock_client,
        ):
            # Should raise validation error
            with pytest.raises(Exception) as exc_info:
                await adapter.generate(prompt="My age", structured_output_schema=schema)
            assert "Response does not match requested schema" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_non_json_response_validation_fails(self):
        """Test that non-JSON responses fail validation when schema is provided."""
        adapter = VertexAdapter("gemini-2.5-pro")

        schema = {"type": "object"}

        mock_client = MagicMock()
        # Set up aio structure
        mock_client.aio = MagicMock()
        mock_client.aio.models = MagicMock()
        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [MagicMock()]
        # Plain text response - should raise JSON decode error
        mock_response.candidates[0].content.parts[
            0
        ].text = "This is plain text, not JSON"
        mock_response.candidates[0].content.parts[0].function_call = None
        # Mock response.text property to return plain text
        mock_response.text = "This is plain text, not JSON"

        # Create async mock for aio client
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch(
            "mcp_second_brain.adapters.vertex.adapter.get_client",
            return_value=mock_client,
        ):
            # Should raise JSON decode error
            with pytest.raises(Exception) as exc_info:
                await adapter.generate(
                    prompt="Return plain text", structured_output_schema=schema
                )
            assert "Response is not valid JSON" in str(exc_info.value)
