"""Unit tests for structured output capability checks."""

import pytest
from mcp_second_brain.adapters.openai.adapter import OpenAIAdapter
# from mcp_second_brain.errors import UnsupportedStructuredOutputError


class TestStructuredOutputCapability:
    """Test that only supported models accept structured output schemas."""

    @pytest.mark.parametrize(
        "model,should_support",
        [
            # Supported models
            ("o3", True),
            ("o3-pro", True),
            ("gpt-4.1", True),
            ("gemini-2.5-pro", True),
            ("gemini-2.5-flash", True),
            # Unsupported models
            ("o3-deep-research", False),  # Research models don't support custom schemas
            ("o4-mini-deep-research", False),
            ("unknown-model", False),
        ],
    )
    @pytest.mark.skip(reason="Requires API mocking")
    async def test_model_capability_check(self, model: str, should_support: bool):
        """Test that models correctly accept or reject structured output schemas."""
        # This test would need proper API mocking to work without real API calls
        pass


class TestStructuredOutputValidation:
    """Test that structured output schemas are validated."""

    @pytest.mark.skip(reason="Schema validation not yet implemented")
    async def test_invalid_schema_rejected(self):
        """Test that invalid JSON schemas are rejected."""
        invalid_schema = {
            "type": "invalid-type",  # Invalid type
            "properties": "not-a-dict",  # Invalid properties
        }

        adapter = OpenAIAdapter("gpt-4.1")

        with pytest.raises(ValueError, match="Invalid JSON schema"):
            await adapter.generate(
                prompt="Test prompt", structured_output_schema=invalid_schema
            )

    @pytest.mark.skip(reason="OpenAI requires properties in schema")
    async def test_empty_schema_allowed(self):
        """Test that empty schema (any JSON) is allowed."""
        # OpenAI requires properties, so this test doesn't apply
        pass
