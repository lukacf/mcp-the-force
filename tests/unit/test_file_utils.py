"""
Unit tests for file utilities including .gitignore handling and file filtering.
"""

import os
from pathlib import Path
import pytest
from mcp_second_brain.utils import fs
from mcp_second_brain.utils.fs import (
    gather_file_paths,
    _is_text_file,
    _is_ignored,
    _parse_gitignore,
)


class TestGitignore:
    """Test .gitignore handling."""

    def test_parse_gitignore(self, tmp_path):
        """Test parsing .gitignore file."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n# Comment\n__pycache__/\n\n.env")

        patterns = _parse_gitignore(gitignore)
        assert patterns == ["*.log", "__pycache__/", ".env"]

    def test_is_ignored(self, tmp_path):
        """Test if files match gitignore patterns."""
        patterns = ["*.log", "__pycache__/", ".env", "build/"]

        # Test files that should be ignored
        assert _is_ignored(tmp_path / "debug.log", patterns, tmp_path)
        assert _is_ignored(tmp_path / "src" / "app.log", patterns, tmp_path)
        assert _is_ignored(tmp_path / "__pycache__" / "module.pyc", patterns, tmp_path)
        assert _is_ignored(tmp_path / ".env", patterns, tmp_path)
        assert _is_ignored(tmp_path / "build" / "output.js", patterns, tmp_path)

        # Test files that should NOT be ignored
        assert not _is_ignored(tmp_path / "main.py", patterns, tmp_path)
        assert not _is_ignored(tmp_path / "README.md", patterns, tmp_path)
        assert not _is_ignored(tmp_path / "src" / "app.py", patterns, tmp_path)


class TestFileDetection:
    """Test text file detection."""

    def test_text_file_by_extension(self, tmp_path):
        """Test text file detection by extension."""
        # Text files
        for ext in [".py", ".js", ".txt", ".md", ".json", ".xml"]:
            f = tmp_path / f"test{ext}"
            f.write_text("content")
            assert _is_text_file(f)

        # Binary files
        for ext in [".jpg", ".exe", ".zip", ".pyc"]:
            f = tmp_path / f"test{ext}"
            f.write_bytes(b"binary")
            assert not _is_text_file(f)

    def test_text_file_by_content(self, tmp_path):
        """Test text file detection by content when no extension."""
        # Text file without extension
        text_file = tmp_path / "textfile"
        text_file.write_text("This is plain text")
        assert _is_text_file(text_file)

        # Binary file without extension
        binary_file = tmp_path / "binaryfile"
        binary_file.write_bytes(b"\x00\x01\x02\x03")
        assert not _is_text_file(binary_file)

    def test_large_file_rejection(self, tmp_path):
        """Test that files over MAX_FILE_SIZE are rejected."""
        large_file = tmp_path / "large.txt"
        large_file.write_text("x" * (fs.MAX_FILE_SIZE + 1))
        assert not _is_text_file(large_file)

    def test_empty_file(self, tmp_path):
        """Test empty file handling."""
        empty = tmp_path / "empty.txt"
        empty.touch()
        assert _is_text_file(empty)


class TestGatherFiles:
    """Test the main gather_file_paths function."""

    def test_gather_single_file(self, tmp_path, monkeypatch):
        """Test gathering a single file."""
        monkeypatch.chdir(tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        files = gather_file_paths([str(test_file)])
        assert len(files) == 1
        assert str(test_file) in files

    def test_gather_directory(self, tmp_path, monkeypatch):
        """Test gathering files from a directory."""
        monkeypatch.chdir(tmp_path)
        # Create some files
        (tmp_path / "main.py").write_text("# main")
        (tmp_path / "utils.py").write_text("# utils")
        (tmp_path / "README.md").write_text("# Readme")
        (tmp_path / "data.json").write_text("{}")

        # Create a binary file that should be skipped
        (tmp_path / "image.jpg").write_bytes(b"\xff\xd8\xff")

        files = gather_file_paths([str(tmp_path)])
        assert len(files) == 4
        assert str(tmp_path / "main.py") in files
        assert str(tmp_path / "utils.py") in files
        assert str(tmp_path / "README.md") in files
        assert str(tmp_path / "data.json") in files
        assert str(tmp_path / "image.jpg") not in files

    def test_gather_with_gitignore(self, tmp_path, monkeypatch):
        """Test that .gitignore is respected."""
        monkeypatch.chdir(tmp_path)
        # Create .gitignore
        (tmp_path / ".gitignore").write_text("*.log\n__pycache__/\nbuild/")

        # Create files
        (tmp_path / "main.py").write_text("# main")
        (tmp_path / "debug.log").write_text("log data")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "main.pyc").write_bytes(b"pyc")
        (tmp_path / "build").mkdir()
        (tmp_path / "build" / "output.js").write_text("js")

        files = gather_file_paths([str(tmp_path)])
        assert len(files) == 2  # .gitignore and main.py
        assert str(tmp_path / "main.py") in files
        assert str(tmp_path / ".gitignore") in files
        assert str(tmp_path / "debug.log") not in files

    def test_skip_common_directories(self, tmp_path, monkeypatch):
        """Test that common directories are skipped."""
        monkeypatch.chdir(tmp_path)
        # Create node_modules
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.json").write_text("{}")

        # Create .git
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("config")

        # Create regular file
        (tmp_path / "app.js").write_text("// app")

        files = gather_file_paths([str(tmp_path)])
        assert len(files) == 1
        assert str(tmp_path / "app.js") in files

    def test_total_size_limit(self, tmp_path, monkeypatch):
        """Test that total size limit is enforced."""
        monkeypatch.chdir(tmp_path)
        # Create many large files
        for i in range(200):
            f = tmp_path / f"file{i}.txt"
            f.write_text("x" * 300_000)  # 300KB each

        files = gather_file_paths([str(tmp_path)])

        # Should stop before gathering all files
        assert len(files) < 200

        # Calculate total size
        total_size = sum(Path(f).stat().st_size for f in files)
        # Allow exceeding by one file (300KB) since check happens before adding
        assert total_size <= fs.MAX_TOTAL_SIZE + 300_000

    def test_nonexistent_path(self, tmp_path, monkeypatch):
        """Test handling of non-existent paths."""
        monkeypatch.chdir(tmp_path)
        files = gather_file_paths([str(tmp_path / "nonexistent")])
        assert files == []

    def test_permission_error_handling(self, tmp_path, monkeypatch):
        """Test handling of permission errors."""
        if os.name == "nt":  # Skip on Windows
            pytest.skip("Permission test not reliable on Windows")
        monkeypatch.chdir(tmp_path)

        # Create a directory with no read permission
        secret_dir = tmp_path / "secret"
        secret_dir.mkdir()
        (secret_dir / "data.txt").write_text("secret")
        secret_dir.chmod(0o000)

        # Should not crash
        gather_file_paths([str(tmp_path)])

        # Restore permissions for cleanup
        secret_dir.chmod(0o755)

    def test_sorted_output(self, tmp_path, monkeypatch):
        """Test that output is sorted."""
        monkeypatch.chdir(tmp_path)
        # Create files in non-alphabetical order
        (tmp_path / "z.txt").write_text("z")
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "m.txt").write_text("m")

        files = gather_file_paths([str(tmp_path)])

        # Should be sorted
        assert files == sorted(files)

    def test_deduplication(self, tmp_path, monkeypatch):
        """Test that duplicate paths are handled."""
        monkeypatch.chdir(tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("test")

        # Pass the same file multiple times
        files = gather_file_paths([str(test_file), str(test_file), str(tmp_path)])

        # Should only appear once
        assert files.count(str(test_file)) == 1


class TestPathTraversal:
    """Tests for path traversal protection."""

    def test_path_traversal_blocked(self, tmp_path, monkeypatch):
        """Paths escaping the project root should be rejected."""
        monkeypatch.chdir(tmp_path)

        outside = tmp_path.parent / "outside.txt"
        outside.write_text("secret")

        files = gather_file_paths([str(tmp_path / ".." / "outside.txt")])

        assert files == []

    def test_safe_path_allowed(self, tmp_path, monkeypatch):
        """Paths inside the project root should be processed."""
        monkeypatch.chdir(tmp_path)

        inside = tmp_path / "inside.txt"
        inside.write_text("ok")

        files = gather_file_paths([str(inside)])

        assert [str(inside)] == files
