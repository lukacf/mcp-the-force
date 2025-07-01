"""
Tests for the count_project_tokens tool.
"""

import pytest
from pathlib import Path
import tempfile
from unittest.mock import patch

from mcp_second_brain.tools.token_count import CountProjectTokens


@pytest.fixture
def temp_project_dir(monkeypatch):
    """Create a temporary project directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Change to the temp directory to make it the project root
        monkeypatch.chdir(project_dir)

        # Create test files
        (project_dir / "file1.txt").write_text("Hello world")
        (project_dir / "file2.py").write_text("def hello():\n    print('Hello')")
        (project_dir / "binary.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (project_dir / "large.txt").write_text("x" * 1_000_000)  # 1MB file

        # Create subdirectory
        subdir = project_dir / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("Nested content")

        # Create .gitignore
        (project_dir / ".gitignore").write_text("ignored.txt\n*.log")
        (project_dir / "ignored.txt").write_text("This should be ignored")
        (project_dir / "test.log").write_text("Also ignored")

        yield project_dir


class TestCountProjectTokens:
    """Test the count_project_tokens tool."""

    async def test_counts_tokens_for_single_file(self, temp_project_dir):
        """Should return correct token count for a single file."""
        tool = CountProjectTokens()
        tool.items = ["file1.txt"]
        result = await tool.generate()

        assert result["total_tokens"] > 0
        # Check that file1.txt is in the results (path may be absolute)
        assert any("file1.txt" in path for path in result["per_file"])
        # Get the token count for file1.txt
        file1_tokens = next(
            v for k, v in result["per_file"].items() if "file1.txt" in k
        )
        assert file1_tokens > 0

    async def test_counts_tokens_for_directory(self, temp_project_dir):
        """Should return token counts for all text files in directory."""
        tool = CountProjectTokens()
        tool.items = ["."]
        result = await tool.generate()

        # Should include text files
        assert any("file1.txt" in path for path in result["per_file"])
        assert any("file2.py" in path for path in result["per_file"])
        assert any("nested.txt" in path for path in result["per_file"])

        # Should have non-zero total
        assert result["total_tokens"] > 0

        # Total should equal sum of individual files
        total_from_files = sum(result["per_file"].values())
        assert result["total_tokens"] == total_from_files

    async def test_skips_binary_files(self, temp_project_dir):
        """Should skip binary files like images."""
        tool = CountProjectTokens()
        tool.items = ["."]
        result = await tool.generate()

        # Binary file should not be included
        assert not any("binary.png" in path for path in result["per_file"])

    async def test_respects_gitignore(self, temp_project_dir):
        """Should skip files matching .gitignore patterns."""
        tool = CountProjectTokens()
        tool.items = ["."]
        result = await tool.generate()

        # Ignored files should not be included
        assert not any("ignored.txt" in path for path in result["per_file"])
        assert not any("test.log" in path for path in result["per_file"])

    async def test_handles_large_files(self, temp_project_dir):
        """Should handle or skip files exceeding size limits."""
        tool = CountProjectTokens()
        tool.items = ["."]
        result = await tool.generate()

        # Large file might be skipped or included depending on MAX_FILE_SIZE
        # Just ensure it doesn't crash
        assert isinstance(result["total_tokens"], int)
        assert isinstance(result["per_file"], dict)

    async def test_rejects_paths_outside_project(self, temp_project_dir):
        """Should reject paths that try to escape project root."""
        tool = CountProjectTokens()
        tool.items = ["../../../etc/passwd"]
        result = await tool.generate()

        # Should get empty results since path is outside project
        assert result["total_tokens"] == 0
        assert len(result["per_file"]) == 0

    async def test_handles_non_utf8_files(self, temp_project_dir):
        """Should handle files with non-UTF8 encoding gracefully."""
        # Create file with invalid UTF-8
        bad_file = temp_project_dir / "bad_encoding.txt"
        bad_file.write_bytes(b"Hello \xff\xfe World")

        tool = CountProjectTokens()
        tool.items = ["bad_encoding.txt"]
        result = await tool.generate()

        # Should process file without crashing
        assert any("bad_encoding.txt" in path for path in result["per_file"])
        assert result["total_tokens"] > 0

    async def test_empty_directory(self, temp_project_dir):
        """Should handle empty directories gracefully."""
        empty_dir = temp_project_dir / "empty"
        empty_dir.mkdir()

        tool = CountProjectTokens()
        tool.items = ["empty"]
        result = await tool.generate()

        assert result["total_tokens"] == 0
        assert len(result["per_file"]) == 0

    async def test_multiple_paths(self, temp_project_dir):
        """Should handle multiple paths in items list."""
        tool = CountProjectTokens()
        tool.items = ["file1.txt", "subdir"]
        result = await tool.generate()

        # Should include file1.txt and nested.txt
        assert any("file1.txt" in path for path in result["per_file"])
        assert any("nested.txt" in path for path in result["per_file"])
        # But not file2.py since we didn't include parent dir
        assert not any("file2.py" in path for path in result["per_file"])

    @patch("mcp_second_brain.utils.token_counter.tiktoken")
    async def test_fallback_when_tiktoken_missing(
        self, mock_tiktoken, temp_project_dir
    ):
        """Should fall back gracefully when tiktoken is not available."""
        # Make tiktoken import fail
        mock_tiktoken.get_encoding.side_effect = ImportError("No tiktoken")

        tool = CountProjectTokens()
        tool.items = ["file1.txt"]
        result = await tool.generate()

        # Should still return a reasonable estimate
        assert result["total_tokens"] > 0
        assert any("file1.txt" in path for path in result["per_file"])
