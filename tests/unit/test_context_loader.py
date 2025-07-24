"""
Tests for the shared context loading functionality.
"""

import pytest
from pathlib import Path
import tempfile
from unittest.mock import patch

from mcp_the_force.utils.context_loader import load_text_files


@pytest.fixture
def temp_files(monkeypatch):
    """Create temporary test files within a mock project root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Change to the temp directory to make it the project root
        monkeypatch.chdir(tmpdir)

        # Create test files
        (root / "small.txt").write_text("Hello world")
        (root / "code.py").write_text("def foo():\n    return 42")
        (root / ".gitignore").write_text("ignored.txt")
        (root / "ignored.txt").write_text("Should be ignored")

        # Binary file
        (root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        yield root


class TestContextLoader:
    """Test the shared context loading functionality."""

    def test_load_single_text_file(self, temp_files):
        """Should load a single text file with content and token count."""
        result = load_text_files([str(temp_files / "small.txt")])

        assert len(result) == 1
        path, content, tokens = result[0]
        # Normalize paths to handle symlinks (e.g., /var -> /private/var on macOS)
        assert Path(path).resolve() == (temp_files / "small.txt").resolve()
        assert content == "Hello world"
        assert tokens > 0  # Should have some token count

    def test_load_multiple_files(self, temp_files):
        """Should load multiple text files."""
        result = load_text_files([str(temp_files)])

        # Should load small.txt and code.py (not ignored.txt or image.png)
        paths = [Path(item[0]).resolve() for item in result]
        assert (temp_files / "small.txt").resolve() in paths
        assert (temp_files / "code.py").resolve() in paths

        # These should not be in the results
        path_strs = [item[0] for item in result]
        assert not any("ignored.txt" in p for p in path_strs)
        assert not any("image.png" in p for p in path_strs)

    def test_skip_binary_files(self, temp_files):
        """Should skip binary files."""
        result = load_text_files([str(temp_files / "image.png")])
        assert len(result) == 0

    def test_handle_read_errors(self, temp_files):
        """Should skip files that can't be read."""
        # Create a file and make it unreadable
        bad_file = temp_files / "unreadable.txt"
        bad_file.write_text("content")
        bad_file.chmod(0o000)

        try:
            result = load_text_files([str(bad_file)])
            # Should skip the file without crashing
            assert len(result) == 0
        finally:
            # Restore permissions for cleanup
            bad_file.chmod(0o644)

    def test_token_counting(self, temp_files):
        """Should return reasonable token counts."""
        result = load_text_files([str(temp_files / "code.py")])

        assert len(result) == 1
        path, content, tokens = result[0]

        # Python code should have more tokens than character count / 4
        # (rough estimate for English text)
        assert tokens > len(content) / 4
        assert tokens < len(content)  # But not more than character count

    def test_returns_sorted_files(self, temp_files):
        """Should return files in sorted order as per gather_file_paths behavior."""
        files = [str(temp_files / "small.txt"), str(temp_files / "code.py")]
        result = load_text_files(files)

        # gather_file_paths returns sorted results
        assert len(result) == 2
        # Files should be sorted: code.py comes before small.txt alphabetically
        assert Path(result[0][0]).name == "code.py"
        assert Path(result[1][0]).name == "small.txt"

    def test_handles_utf8_with_errors(self, temp_files):
        """Should handle non-UTF8 bytes gracefully."""
        bad_file = temp_files / "bad_utf8.txt"
        bad_file.write_bytes(b"Hello \xff\xfe World")

        result = load_text_files([str(bad_file)])
        assert len(result) == 1
        path, content, tokens = result[0]

        # Verify correct file was processed
        assert Path(path).resolve() == bad_file.resolve()

        # Should have processed the file, possibly with replacement chars
        assert "Hello" in content
        assert "World" in content
        assert tokens > 0

    def test_removes_null_bytes(self, temp_files):
        """Should remove null bytes from content."""
        null_file = temp_files / "with_nulls.txt"
        null_file.write_bytes(b"Hello\x00World")

        result = load_text_files([str(null_file)])
        assert len(result) == 1
        path, content, tokens = result[0]

        # Verify correct file was processed
        assert Path(path).resolve() == null_file.resolve()

        assert content == "HelloWorld"  # Null byte removed
        assert "\x00" not in content

    @patch("mcp_the_force.utils.context_loader.count_tokens")
    def test_uses_token_counter(self, mock_count_tokens, temp_files):
        """Should use the token counter utility."""
        mock_count_tokens.return_value = 42

        result = load_text_files([str(temp_files / "small.txt")])

        # Should have called count_tokens
        mock_count_tokens.assert_called_once()
        # Should pass content as list
        call_args = mock_count_tokens.call_args[0][0]
        assert isinstance(call_args, list)
        assert len(call_args) == 1
        assert call_args[0] == "Hello world"

        # Should use the returned token count
        assert result[0][2] == 42
