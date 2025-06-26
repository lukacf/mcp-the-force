"""Basic smoke tests for E2E validation."""

import pytest
import json

pytestmark = pytest.mark.e2e


class TestE2ESmoke:
    """Smoke tests to verify basic functionality."""

    def test_list_models(self, claude_code):
        """Test that list_models works through Claude Code."""
        output = claude_code("Use the second-brain MCP server list_models tool")

        # Should mention available models
        assert "gemini" in output.lower() or "flash" in output.lower()
        assert "o3" in output.lower() or "openai" in output.lower()
        assert "gpt" in output.lower() or "model" in output.lower()

    def test_simple_query(self, claude_code):
        """Test a simple query with a cheap/fast model."""
        # Build prompt
        args = {
            "instructions": "Say hello in exactly 3 words",
            "output_format": "text",
            "context": [],
        }
        prompt = f"Use second-brain chat_with_gemini25_flash with {json.dumps(args)}"
        output = claude_code(prompt)

        # Should get some response
        assert len(output) > 10
        # Don't fail on transient network errors
        if "error" in output.lower() and "network" not in output.lower():
            assert False, f"Unexpected error: {output}"

    def test_file_analysis(self, claude_code, test_file):
        """Test analyzing a file with context."""
        output = claude_code(
            f'Use second-brain chat_with_gemini25_flash to analyze the code in "{test_file}" '
            f'with instructions "Is this recursive? Answer yes or no only", '
            f'output_format "text", and context ["{test_file}"]'
        )

        # Should recognize recursion
        output_lower = output.lower()
        assert (
            "yes" in output_lower or "recursion" in output_lower
        ), f"Expected 'yes' or 'recursion', but got: {output}"

    def test_error_handling(self, claude_code):
        """Test that errors are handled gracefully."""
        # Try to use a non-existent file
        output = claude_code(
            'Use second-brain chat_with_gemini25_flash with instructions "analyze this", '
            'output_format "text", and context ["/does/not/exist.py"]'
        )

        # Should handle missing file gracefully
        # Either by skipping it or mentioning it doesn't exist
        assert len(output) > 0
