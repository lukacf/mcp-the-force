"""E2E tests for attachment functionality across all models."""

import pytest
import json
import tempfile
import os
import re
from typing import Any


# JSON parsing utilities
def safe_json(raw: str) -> Any:
    """
    Best-effort JSON extractor that handles edge cases like empty responses,
    markdown code fences, and control characters.
    """
    if not raw or not raw.strip():
        raise AssertionError("Model returned an empty response")

    # Simple JSON parsing for now - can be enhanced if needed
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        # Try to extract JSON from markdown code fences
        cleaned = re.sub(r"```(?:json)?|```", "", raw, flags=re.I).strip()
        if cleaned:
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass
        raise AssertionError(f"Failed to parse JSON from response: {raw!r}, error: {e}")


pytestmark = pytest.mark.e2e

# All models that should support attachments
MODELS_WITH_ATTACHMENTS = [
    "chat_with_gpt4_1",
    "chat_with_o3",
    # "chat_with_o3_pro",  # Too slow for regular testing
    "chat_with_gemini25_pro",
    "chat_with_gemini25_flash",
]

# Models that support web search (for testing search tools)
MODELS_WITH_WEB_SEARCH = [
    "chat_with_gpt4_1",
    "chat_with_o3",
    "chat_with_o3_pro",
]


class TestAttachmentsAllModels:
    """Test attachment functionality works for all models that support it."""

    @pytest.mark.parametrize("model", MODELS_WITH_ATTACHMENTS)
    def test_attachment_search_available(self, claude_code, model):
        """Test that search_session_attachments is available when attachments are provided."""
        # Create a test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("ATTACHMENT_MARKER::TEST-12345")
            test_file = f.name

        try:
            # Define schema for structured output
            is_openai = any(x in model for x in ["o3", "gpt4_1"])

            schema = {
                "type": "object",
                "properties": {
                    "has_tool": {"type": "boolean"},
                    "tool_name": {"type": "string"},
                },
                "required": ["has_tool", "tool_name"],
                "additionalProperties": False,
            }

            # Ask the model whether it can use the attachment-search tool
            args = {
                "instructions": "Check if you have access to a tool called 'search_session_attachments' that allows you to search through attached files.",
                "output_format": "Return JSON with 'has_tool' (boolean) and 'tool_name' (the exact tool name if available, empty string if not)",
                "context": [],
                "attachments": [test_file],
                "session_id": f"{model}-tools-with-attachments",
                "structured_output_schema": schema,
            }

            # Add OpenAI-specific instructions
            openai_note = ""
            if is_openai:
                openai_note = " IMPORTANT: The schema has 'additionalProperties': false at every object level as required for OpenAI models."

            prompt = f"Use second-brain {model} with {json.dumps(args)} and respond ONLY with the exact JSON response you receive, nothing else.{openai_note}"
            response = claude_code(prompt)

            # Parse the structured response
            result = safe_json(response)
            assert (
                result["has_tool"] is True
            ), f"{model} should have search_session_attachments when attachments are provided"
            assert (
                result["tool_name"] == "search_session_attachments"
            ), f"{model} should report correct tool name"

        finally:
            os.unlink(test_file)

    @pytest.mark.parametrize("model", MODELS_WITH_ATTACHMENTS)
    def test_attachment_search_not_available_without_attachments(
        self, claude_code, model
    ):
        """Test that search_session_attachments is NOT available without attachments."""
        # Define schema for structured output
        is_openai = any(x in model for x in ["o3", "gpt4_1"])

        schema = {
            "type": "object",
            "properties": {
                "has_tool": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["has_tool", "reason"],
            "additionalProperties": False,
        }

        # Ask the model the same question but without attachments
        args = {
            "instructions": "Check if you have access to a tool called 'search_session_attachments' that allows you to search through attached files.",
            "output_format": "Return JSON with 'has_tool' (boolean) and 'reason' (brief explanation)",
            "context": [],
            "session_id": f"{model}-tools-no-attachments",
            "structured_output_schema": schema,
        }

        # Add OpenAI-specific instructions
        openai_note = ""
        if is_openai:
            openai_note = " IMPORTANT: The schema requires 'additionalProperties': false as mandated for OpenAI models."

        prompt = f"Use second-brain {model} with {json.dumps(args)} and respond ONLY with the exact JSON response you receive, nothing else.{openai_note}"
        response = claude_code(prompt)

        # Parse the structured response
        result = safe_json(response)
        assert (
            result["has_tool"] is False
        ), f"{model} should NOT have search_session_attachments without attachments"

    @pytest.mark.parametrize("model", MODELS_WITH_ATTACHMENTS)
    def test_can_find_content_in_attachments(self, claude_code, model):
        """Test that models can actually search and find content in attachments."""
        # Create a test file with unique content
        unique_marker = f"UNIQUE-MARKER-{model.upper()}-98765"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(f"ATTACHMENT_MARKER::{unique_marker}")
            test_file = f.name

        try:
            # Define schema for structured output
            is_openai = any(x in model for x in ["o3", "gpt4_1"])

            schema = {
                "type": "object",
                "properties": {
                    "found": {"type": "boolean"},
                    "evidence": {"type": "string"},
                },
                "required": ["found", "evidence"],
                "additionalProperties": False,
            }

            # Ask the model to find the unique marker
            args = {
                "instructions": f"Search the attached file for '{unique_marker}' and tell me if you found it.",
                "output_format": "Return JSON with 'found' (boolean) and 'evidence' (quote from file if found, empty string if not)",
                "context": [],
                "attachments": [test_file],
                "session_id": f"{model}-search-content",
                "structured_output_schema": schema,
            }

            # Add OpenAI-specific instructions
            openai_note = ""
            if is_openai:
                openai_note = " IMPORTANT: Return valid JSON following the schema with 'additionalProperties': false."

            prompt = f"Use second-brain {model} with {json.dumps(args)} and respond ONLY with the exact JSON response you receive, nothing else.{openai_note}"
            response = claude_code(prompt)

            # Parse the structured response
            result = safe_json(response)
            assert (
                result["found"] is True
            ), f"{model} should be able to find content in attachments"
            assert (
                unique_marker in result["evidence"]
            ), f"{model} should include the marker in evidence"

        finally:
            os.unlink(test_file)

    @pytest.mark.parametrize("model", MODELS_WITH_ATTACHMENTS)
    def test_cannot_find_content_without_attachments(self, claude_code, model):
        """Test that models cannot find content when no attachments are provided."""
        unique_marker = f"NONEXISTENT-MARKER-{model.upper()}-11111"

        # Define schema for structured output
        is_openai = any(x in model for x in ["o3", "gpt4_1"])

        schema = {
            "type": "object",
            "properties": {
                "found": {"type": "boolean"},
                "explanation": {"type": "string"},
            },
            "required": ["found", "explanation"],
            "additionalProperties": False,
        }

        # Ask the model to find content WITHOUT providing attachments
        args = {
            "instructions": f"Search for '{unique_marker}' and tell me if you found it.",
            "output_format": "Return JSON with 'found' (boolean) and 'explanation' (why found/not found)",
            "context": [],
            "session_id": f"{model}-search-no-attachments",
            "structured_output_schema": schema,
        }

        # Add OpenAI-specific instructions
        openai_note = ""
        if is_openai:
            openai_note = " IMPORTANT: Adhere to the JSON schema with 'additionalProperties': false at object level."

        prompt = f"Use second-brain {model} with {json.dumps(args)} and respond ONLY with the exact JSON response you receive, nothing else.{openai_note}"
        response = claude_code(prompt)

        # Parse the structured response
        result = safe_json(response)
        assert (
            result["found"] is False
        ), f"{model} should not find content without attachments"

    def test_feature_parity_attachments(self, claude_code):
        """Test that all expected models support attachments parameter."""
        # This is a meta-test that verifies our expectations
        response = claude_code("Use second-brain list_models")

        # Parse the response to find which models were listed
        response_lower = response.lower()

        for model in MODELS_WITH_ATTACHMENTS:
            # Convert model name format (chat_with_gpt4_1 -> gpt-4.1 or gpt4_1)
            model_variants = [
                model.replace("chat_with_", "").replace("_", "-"),
                model.replace("chat_with_", "").replace("_", "."),
                model.replace("chat_with_", ""),
            ]

            assert any(
                variant in response_lower for variant in model_variants
            ), f"Model {model} should be listed in available models"
