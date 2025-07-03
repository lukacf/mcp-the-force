"""E2E tests for token counting functionality."""

import pytest

pytestmark = pytest.mark.e2e


class TestTokenCounter:
    """Test token counting tool through Claude."""

    def test_count_tokens_single_file(self, claude_code):
        """Test counting tokens for a single file."""
        response = claude_code(
            "Use second-brain count_project_tokens to count tokens in the README.md file"
        )

        # Should mention token count
        assert "token" in response.lower()
        # Should mention the file
        assert "readme" in response.lower()
        # Should contain a number
        assert any(char.isdigit() for char in response)

    def test_count_tokens_directory(self, claude_code):
        """Test counting tokens for a directory."""
        response = claude_code(
            "Use second-brain count_project_tokens to count tokens in the mcp_second_brain/utils directory"
        )

        # Should mention token count
        assert "token" in response.lower()
        # Should mention multiple files or total
        assert any(word in response.lower() for word in ["total", "files", "multiple"])
        # Should contain numbers
        assert any(char.isdigit() for char in response)

    def test_count_tokens_multiple_items(self, claude_code):
        """Test counting tokens for multiple files and directories."""
        response = claude_code(
            "Use second-brain count_project_tokens to count tokens in both pyproject.toml and the tests/unit directory"
        )

        # Should mention both items
        assert "pyproject.toml" in response.lower()
        assert "tests/unit" in response.lower() or "test" in response.lower()
        # Should mention tokens
        assert "token" in response.lower()

    def test_count_tokens_with_gitignore(self, claude_code):
        """Test that token counting respects .gitignore patterns."""
        response = claude_code(
            "Use second-brain count_project_tokens to count tokens in the mcp_second_brain directory. "
            "Tell me if it includes or excludes __pycache__ directories and respects .gitignore patterns."
        )

        # Should mention exclusion of ignored files
        assert any(
            word in response.lower()
            for word in ["exclude", "ignore", "skip", "not include"]
        )
        # Should mention __pycache__ or gitignore
        assert "__pycache__" in response.lower() or "gitignore" in response.lower()

    def test_count_tokens_formatted_output(self, claude_code):
        """Test that token counting provides well-formatted output."""
        response = claude_code(
            "Use second-brain count_project_tokens to count tokens in pyproject.toml and "
            "format the output showing the file name and token count clearly"
        )

        # Should include the filename
        assert "pyproject.toml" in response
        # Should include token count with a number
        assert "token" in response.lower()
        # Should have clear formatting (colon, dash, or similar)
        assert any(sep in response for sep in [":", "-", "•", "*"])

    def test_count_tokens_error_handling(self, claude_code):
        """Test token counting with non-existent file."""
        response = claude_code(
            "Use second-brain count_project_tokens to count tokens for the file "
            "non_existent_file_12345.txt. Report the result."
        )

        # Should indicate no tokens, zero tokens, or file not found
        assert any(
            phrase in response.lower()
            for phrase in [
                "0 token",
                "zero token",
                "no token",
                "no file",
                "not found",
                "doesn't exist",
                "empty",
                "none",
            ]
        ), f"Expected error handling response but got: {response}"

    def test_count_tokens_binary_files(self, claude_code):
        """Test that binary files are excluded from token counting."""
        # First, let's create a scenario with binary files
        response = claude_code(
            "Use second-brain count_project_tokens to count tokens in the tests directory. "
            "Tell me if it skips binary files like .pyc or image files."
        )

        # Should mention skipping or excluding binary files
        assert any(
            word in response.lower()
            for word in [
                "skip",
                "exclude",
                "ignore",
                "binary",
                "text file",
                "text only",
            ]
        )
