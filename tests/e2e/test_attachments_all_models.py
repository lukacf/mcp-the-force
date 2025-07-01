"""E2E tests for attachment functionality across all models."""

import pytest
import json
import tempfile
import os

pytestmark = pytest.mark.e2e

# All models that should support attachments
MODELS_WITH_ATTACHMENTS = [
    "chat_with_gpt4_1",
    "chat_with_o3",
    "chat_with_o3_pro",
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
            f.write("TEST-MARKER-12345")
            test_file = f.name

        try:
            # Ask the model to list its available tools
            args = {
                "instructions": "List all the tools/functions you have access to. Just list the function names.",
                "output_format": "List each tool name on a separate line",
                "context": [],
                "attachments": [test_file],
                "session_id": f"{model}-tools-with-attachments",
            }

            prompt = f"Use second-brain {model} with {json.dumps(args)}"
            response = claude_code(prompt)

            # Verify search_session_attachments is available
            assert (
                "search_session_attachments" in response.lower()
            ), f"{model} should have search_session_attachments when attachments are provided"

            # Also verify search_project_memory is still available
            assert (
                "search_project_memory" in response.lower()
            ), f"{model} should still have search_project_memory"

        finally:
            os.unlink(test_file)

    @pytest.mark.parametrize("model", MODELS_WITH_ATTACHMENTS)
    def test_attachment_search_not_available_without_attachments(
        self, claude_code, model
    ):
        """Test that search_session_attachments is NOT available without attachments."""
        # Ask the model to list its available tools WITHOUT attachments
        args = {
            "instructions": "List all the tools/functions you have access to. Just list the function names.",
            "output_format": "List each tool name on a separate line",
            "context": [],
            "session_id": f"{model}-tools-no-attachments",
        }

        prompt = f"Use second-brain {model} with {json.dumps(args)}"
        response = claude_code(prompt)

        # Verify search_session_attachments is NOT available
        assert (
            "search_session_attachments" not in response.lower()
        ), f"{model} should NOT have search_session_attachments without attachments"

        # But search_project_memory should still be available
        assert (
            "search_project_memory" in response.lower()
        ), f"{model} should have search_project_memory"

    @pytest.mark.parametrize("model", MODELS_WITH_ATTACHMENTS)
    def test_can_find_content_in_attachments(self, claude_code, model):
        """Test that models can actually search and find content in attachments."""
        # Create a test file with unique content
        unique_marker = f"UNIQUE-MARKER-{model.upper()}-98765"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(f"This file contains a secret: {unique_marker}")
            test_file = f.name

        try:
            # Ask the model to find the unique marker
            args = {
                "instructions": f"Search the attached file for '{unique_marker}' and tell me if you found it.",
                "output_format": "Reply with YES if found, NO if not found",
                "context": [],
                "attachments": [test_file],
                "session_id": f"{model}-search-content",
            }

            prompt = f"Use second-brain {model} with {json.dumps(args)}"
            response = claude_code(prompt)

            # The model should find the marker
            assert (
                "yes" in response.lower()
            ), f"{model} should be able to find content in attachments"

        finally:
            os.unlink(test_file)

    @pytest.mark.parametrize("model", MODELS_WITH_ATTACHMENTS)
    def test_cannot_find_content_without_attachments(self, claude_code, model):
        """Test that models cannot find content when no attachments are provided."""
        unique_marker = f"NONEXISTENT-MARKER-{model.upper()}-11111"

        # Ask the model to find content WITHOUT providing attachments
        args = {
            "instructions": f"Search for '{unique_marker}' and tell me if you found it.",
            "output_format": "Reply with YES if found, NO if not found",
            "context": [],
            "session_id": f"{model}-search-no-attachments",
        }

        prompt = f"Use second-brain {model} with {json.dumps(args)}"
        response = claude_code(prompt)

        # The model should NOT find the marker
        assert (
            "no" in response.lower()
            or "not found" in response.lower()
            or "cannot" in response.lower()
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
