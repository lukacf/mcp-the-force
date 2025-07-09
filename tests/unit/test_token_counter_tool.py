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
        assert result["total_files"] == 1
        # Check that file1.txt is in the largest_files
        assert len(result["largest_files"]) == 1
        assert any("file1.txt" in f["path"] for f in result["largest_files"])
        # Get the token count for file1.txt
        file1_tokens = next(
            f["tokens"] for f in result["largest_files"] if "file1.txt" in f["path"]
        )
        assert file1_tokens > 0

    async def test_counts_tokens_for_directory(self, temp_project_dir):
        """Should return token counts for all text files in directory."""
        tool = CountProjectTokens()
        tool.items = ["."]
        result = await tool.generate()

        # Should have correct number of files
        assert result["total_files"] >= 3  # At least file1.txt, file2.py, nested.txt

        # Should include text files in largest_files
        file_paths = [f["path"] for f in result["largest_files"]]
        assert any("file1.txt" in path for path in file_paths)
        assert any("file2.py" in path for path in file_paths)
        # nested.txt might not be in top N if there are other larger files

        # Should have non-zero total
        assert result["total_tokens"] > 0

        # Should have directory aggregation
        assert len(result["largest_directories"]) > 0
        # Check that subdir is included
        dir_paths = [d["path"] for d in result["largest_directories"]]
        assert any("subdir" in path for path in dir_paths)

    async def test_skips_binary_files(self, temp_project_dir):
        """Should skip binary files like images."""
        tool = CountProjectTokens()
        tool.items = ["."]
        result = await tool.generate()

        # Binary file should not be included in largest_files
        file_paths = [f["path"] for f in result["largest_files"]]
        assert not any("binary.png" in path for path in file_paths)

    async def test_respects_gitignore(self, temp_project_dir):
        """Should skip files matching .gitignore patterns."""
        tool = CountProjectTokens()
        tool.items = ["."]
        result = await tool.generate()

        # Ignored files should not be included in largest_files
        file_paths = [f["path"] for f in result["largest_files"]]
        assert not any("ignored.txt" in path for path in file_paths)
        assert not any("test.log" in path for path in file_paths)

    async def test_handles_large_files(self, temp_project_dir):
        """Should handle or skip files exceeding size limits."""
        tool = CountProjectTokens()
        tool.items = ["."]
        result = await tool.generate()

        # Large file might be skipped or included depending on MAX_FILE_SIZE
        # Just ensure it doesn't crash
        assert isinstance(result["total_tokens"], int)
        assert isinstance(result["total_files"], int)
        assert isinstance(result["largest_files"], list)
        assert isinstance(result["largest_directories"], list)

    @pytest.mark.skip(reason="Path traversal protection disabled for MCP server usage")
    async def test_rejects_paths_outside_project(self, temp_project_dir):
        """Should reject paths that try to escape project root."""
        tool = CountProjectTokens()
        tool.items = ["../../../etc/passwd"]
        result = await tool.generate()

        # Should get empty results since path is outside project
        assert result["total_tokens"] == 0
        assert result["total_files"] == 0
        assert len(result["largest_files"]) == 0
        assert len(result["largest_directories"]) == 0

    async def test_handles_non_utf8_files(self, temp_project_dir):
        """Should handle files with non-UTF8 encoding gracefully."""
        # Create file with invalid UTF-8
        bad_file = temp_project_dir / "bad_encoding.txt"
        bad_file.write_bytes(b"Hello \xff\xfe World")

        tool = CountProjectTokens()
        tool.items = ["bad_encoding.txt"]
        result = await tool.generate()

        # Should process file without crashing
        assert result["total_files"] == 1
        file_paths = [f["path"] for f in result["largest_files"]]
        assert any("bad_encoding.txt" in path for path in file_paths)
        assert result["total_tokens"] > 0

    async def test_empty_directory(self, temp_project_dir):
        """Should handle empty directories gracefully."""
        empty_dir = temp_project_dir / "empty"
        empty_dir.mkdir()

        tool = CountProjectTokens()
        tool.items = ["empty"]
        result = await tool.generate()

        assert result["total_tokens"] == 0
        assert result["total_files"] == 0
        assert len(result["largest_files"]) == 0
        assert len(result["largest_directories"]) == 0

    async def test_multiple_paths(self, temp_project_dir):
        """Should handle multiple paths in items list."""
        tool = CountProjectTokens()
        tool.items = ["file1.txt", "subdir"]
        result = await tool.generate()

        # Should include file1.txt and nested.txt
        assert result["total_files"] == 2
        file_paths = [f["path"] for f in result["largest_files"]]
        assert any("file1.txt" in path for path in file_paths)
        assert any("nested.txt" in path for path in file_paths)
        # But not file2.py since we didn't include parent dir
        assert not any("file2.py" in path for path in file_paths)

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
        assert result["total_files"] == 1
        file_paths = [f["path"] for f in result["largest_files"]]
        assert any("file1.txt" in path for path in file_paths)

    async def test_top_n_parameter(self, temp_project_dir):
        """Should respect the top_n parameter."""
        # Create more files than default top_n
        for i in range(15):
            (temp_project_dir / f"file{i}.txt").write_text(f"Content {i}" * (i + 1))

        tool = CountProjectTokens()
        tool.items = ["."]
        tool.top_n = 5  # Request only top 5
        result = await tool.generate()

        # Should only return 5 files and directories
        assert len(result["largest_files"]) <= 5
        assert len(result["largest_directories"]) <= 5

        # Total files should still count all files
        assert result["total_files"] >= 15

    async def test_directory_aggregation(self, temp_project_dir):
        """Should correctly aggregate tokens by directory."""
        # Create nested directory structure
        deep_dir = temp_project_dir / "level1" / "level2" / "level3"
        deep_dir.mkdir(parents=True)

        # Add files at different levels
        (temp_project_dir / "level1" / "file1.txt").write_text("Level 1 content" * 10)
        (temp_project_dir / "level1" / "level2" / "file2.txt").write_text(
            "Level 2 content" * 20
        )
        (deep_dir / "file3.txt").write_text("Level 3 content" * 30)

        tool = CountProjectTokens()
        tool.items = ["level1"]
        result = await tool.generate()

        # Should have directories in the aggregation

        # level1 should have the most tokens (includes all subdirs)
        level1_dir = next(
            (
                d
                for d in result["largest_directories"]
                if "level1" in d["path"] and "level2" not in d["path"]
            ),
            None,
        )
        assert level1_dir is not None

        # level2 should have fewer tokens
        level2_dir = next(
            (
                d
                for d in result["largest_directories"]
                if "level2" in d["path"] and "level3" not in d["path"]
            ),
            None,
        )
        if level2_dir:
            assert level2_dir["tokens"] < level1_dir["tokens"]

        # All directories should have correct file counts
        for dir_info in result["largest_directories"]:
            assert dir_info["file_count"] > 0
