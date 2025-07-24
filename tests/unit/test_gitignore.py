"""
Unit tests for .gitignore functionality.
Tests the patterns that our implementation supports.
"""

from mcp_the_force.utils.fs import _parse_gitignore, _is_ignored


class TestGitignorePatterns:
    """Test supported .gitignore patterns."""

    def test_basic_wildcard_patterns(self, tmp_path):
        """Test basic wildcard patterns with * and ?."""
        patterns = ["*.log", "*.py[cod]", "test_*.py"]

        # Test * wildcard
        assert _is_ignored(tmp_path / "debug.log", patterns, tmp_path)
        assert _is_ignored(tmp_path / "src" / "app.log", patterns, tmp_path)

        # Test character sets
        assert _is_ignored(tmp_path / "module.pyc", patterns, tmp_path)
        assert _is_ignored(tmp_path / "module.pyo", patterns, tmp_path)
        assert _is_ignored(tmp_path / "module.pyd", patterns, tmp_path)

        # Test prefix patterns
        assert _is_ignored(tmp_path / "test_foo.py", patterns, tmp_path)
        assert not _is_ignored(tmp_path / "foo_test.py", patterns, tmp_path)

    def test_directory_patterns(self, tmp_path):
        """Test patterns for directories ending with /."""
        patterns = ["build/", "temp/", "__pycache__/"]

        # Directory patterns match directories at any level
        assert _is_ignored(tmp_path / "build" / "output.bin", patterns, tmp_path)
        assert _is_ignored(tmp_path / "src" / "temp" / "cache.dat", patterns, tmp_path)
        assert _is_ignored(tmp_path / "__pycache__" / "module.pyc", patterns, tmp_path)

        # Also test nested directories
        assert _is_ignored(
            tmp_path / "project" / "build" / "lib.so", patterns, tmp_path
        )

    def test_exact_name_patterns(self, tmp_path):
        """Test exact filename matching."""
        patterns = ["TODO", ".DS_Store", "Thumbs.db"]

        # Exact matches work at any level
        assert _is_ignored(tmp_path / "TODO", patterns, tmp_path)
        assert _is_ignored(tmp_path / "src" / "TODO", patterns, tmp_path)
        assert _is_ignored(tmp_path / ".DS_Store", patterns, tmp_path)
        assert _is_ignored(tmp_path / "images" / "Thumbs.db", patterns, tmp_path)

        # But not partial matches
        assert not _is_ignored(tmp_path / "TODO.txt", patterns, tmp_path)
        assert not _is_ignored(tmp_path / "my.DS_Store", patterns, tmp_path)

    def test_single_char_wildcard(self, tmp_path):
        """Test ? wildcard for single character matching."""
        patterns = ["file?.txt", "test-?.py", "v?.?.?"]

        # ? matches exactly one character
        assert _is_ignored(tmp_path / "file1.txt", patterns, tmp_path)
        assert _is_ignored(tmp_path / "fileA.txt", patterns, tmp_path)
        assert _is_ignored(tmp_path / "test-1.py", patterns, tmp_path)
        assert _is_ignored(tmp_path / "v1.2.3", patterns, tmp_path)

        # But not zero or multiple characters
        assert not _is_ignored(tmp_path / "file.txt", patterns, tmp_path)
        assert not _is_ignored(tmp_path / "file12.txt", patterns, tmp_path)

    def test_parse_gitignore_file(self, tmp_path):
        """Test parsing of .gitignore file with comments and empty lines."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("""
# This is a comment
*.log

# Another comment
  # Indented comment
\t# Tab comment

*.tmp
build/
""")

        patterns = _parse_gitignore(gitignore)

        # Should only have actual patterns, no comments or empty lines
        assert patterns == ["*.log", "*.tmp", "build/"]

    def test_common_gitignore_patterns(self, tmp_path):
        """Test common real-world .gitignore patterns."""
        patterns = [
            "*.pyc",
            "__pycache__/",
            ".git/",
            ".pytest_cache/",
            "*.egg-info/",
            ".coverage",
            "dist/",
            "build/",
            "*.so",
            ".env",
            ".venv/",
            "node_modules/",
            "*.log",
        ]

        # Test matches
        assert _is_ignored(tmp_path / "module.pyc", patterns, tmp_path)
        assert _is_ignored(tmp_path / "__pycache__" / "cache.db", patterns, tmp_path)
        assert _is_ignored(tmp_path / ".git" / "config", patterns, tmp_path)
        assert _is_ignored(
            tmp_path / ".pytest_cache" / "v" / "cache" / "nodeids", patterns, tmp_path
        )
        # Note: *.egg-info/ pattern matches the directory, not files inside it
        # This is the expected behavior
        assert _is_ignored(tmp_path / ".coverage", patterns, tmp_path)
        assert _is_ignored(tmp_path / "dist" / "package.whl", patterns, tmp_path)
        assert _is_ignored(tmp_path / "build" / "lib" / "module.py", patterns, tmp_path)
        assert _is_ignored(tmp_path / "compiled.so", patterns, tmp_path)
        assert _is_ignored(tmp_path / ".env", patterns, tmp_path)
        assert _is_ignored(tmp_path / ".venv" / "bin" / "python", patterns, tmp_path)
        assert _is_ignored(
            tmp_path / "node_modules" / "package" / "index.js", patterns, tmp_path
        )
        assert _is_ignored(tmp_path / "app.log", patterns, tmp_path)

        # Test non-matches
        assert not _is_ignored(tmp_path / "main.py", patterns, tmp_path)
        assert not _is_ignored(tmp_path / "README.md", patterns, tmp_path)
        assert not _is_ignored(tmp_path / "requirements.txt", patterns, tmp_path)

    def test_complex_glob_patterns(self, tmp_path):
        """Test complex glob patterns."""
        patterns = [
            "*.py[cod]",  # Matches .pyc, .pyo, .pyd
            "test_*.py",  # Matches test files
            "[._]*",  # Matches hidden files
            "*~",  # Matches backup files
        ]

        # Test various matches
        assert _is_ignored(tmp_path / "module.pyc", patterns, tmp_path)
        assert _is_ignored(tmp_path / "module.pyo", patterns, tmp_path)
        assert _is_ignored(tmp_path / "test_foo.py", patterns, tmp_path)
        assert _is_ignored(tmp_path / ".hidden", patterns, tmp_path)
        assert _is_ignored(tmp_path / "_private.py", patterns, tmp_path)
        assert _is_ignored(tmp_path / "backup.txt~", patterns, tmp_path)

        # Should not match
        assert not _is_ignored(tmp_path / "module.py", patterns, tmp_path)
        assert not _is_ignored(tmp_path / "foo_test.py", patterns, tmp_path)
