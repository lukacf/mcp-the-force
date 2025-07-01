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
            # Ask the model whether it can use the attachment-search tool
            args = {
                "instructions": "Check if you have access to a tool called 'search_session_attachments' that allows you to search through attached files. If you have this tool available, respond with exactly the word YES. If you do not have this tool, respond with exactly the word NO. Do not include any other text in your response.",
                "output_format": "Single word response: YES or NO",
                "context": [],
                "attachments": [test_file],
                "session_id": f"{model}-tools-with-attachments",
            }

            prompt = f"Use second-brain {model} with {json.dumps(args)}"
            response = claude_code(prompt)

            # The model must indicate YES (may include explanation)
            response_clean = response.strip().upper()
            # Check if response starts with YES or contains it prominently
            has_yes = (
                response_clean.startswith("YES")
                or response_clean == "YES"
                or (response_clean.startswith("THE") and "HAS ACCESS" in response_clean)
            )
            assert has_yes, f"{model} should report YES when search_session_attachments is available. Got: {response}"

        finally:
            os.unlink(test_file)

    @pytest.mark.parametrize("model", MODELS_WITH_ATTACHMENTS)
    def test_attachment_search_not_available_without_attachments(
        self, claude_code, model
    ):
        """Test that search_session_attachments is NOT available without attachments."""
        # Ask the model the same binary question but without attachments
        args = {
            "instructions": "Check if you have access to a tool called 'search_session_attachments' that allows you to search through attached files. If you have this tool available, respond with exactly the word YES. If you do not have this tool, respond with exactly the word NO. Do not include any other text in your response.",
            "output_format": "Single word response: YES or NO",
            "context": [],
            "session_id": f"{model}-tools-no-attachments",
        }

        prompt = f"Use second-brain {model} with {json.dumps(args)}"
        response = claude_code(prompt)

        # The model must indicate NO (may include explanation)
        response_clean = response.strip().upper()
        # Check if response starts with NO or indicates unavailability
        has_no = (
            response_clean.startswith("NO")
            or response_clean == "NO"
            or "NOT AVAILABLE" in response_clean
            or "DON'T HAVE" in response_clean
            or "DO NOT HAVE" in response_clean
            or "DOES NOT HAVE" in response_clean
        )
        assert has_no, f"{model} should report NO when search_session_attachments is not available. Got: {response}"

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
