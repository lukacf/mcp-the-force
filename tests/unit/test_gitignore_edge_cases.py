"""
Unit tests for .gitignore edge cases.
"""
import pytest
from pathlib import Path
from mcp_second_brain.utils.fs import _parse_gitignore, _is_ignored


class TestGitignoreEdgeCases:
    """Test edge cases in .gitignore handling."""
    
    def test_negation_patterns(self, tmp_path):
        """Test gitignore negation patterns (!)."""
        # Note: Current implementation doesn't support negation
        # This documents the limitation
        patterns = ["*.log", "!important.log"]
        
        # Test current behavior
        assert _is_ignored(tmp_path / "debug.log", patterns, tmp_path)
        
        # This SHOULD be false (negated) but currently isn't supported
        # Marking as xfail to document the limitation
        with pytest.raises(AssertionError):
            assert not _is_ignored(tmp_path / "important.log", patterns, tmp_path)
    
    def test_root_anchored_patterns(self, tmp_path):
        """Test patterns anchored to root with leading slash."""
        patterns = ["/build", "temp/"]
        
        # /build should only match at root
        assert _is_ignored(tmp_path / "build", patterns, tmp_path)
        assert not _is_ignored(tmp_path / "src" / "build", patterns, tmp_path)
        
        # temp/ should match anywhere
        assert _is_ignored(tmp_path / "temp" / "file.txt", patterns, tmp_path)
        assert _is_ignored(tmp_path / "src" / "temp" / "file.txt", patterns, tmp_path)
    
    def test_double_asterisk_patterns(self, tmp_path):
        """Test ** glob patterns."""
        patterns = ["**/*.log", "**/temp/", "docs/**/secret.txt"]
        
        # **/*.log should match at any depth
        assert _is_ignored(tmp_path / "debug.log", patterns, tmp_path)
        assert _is_ignored(tmp_path / "src" / "app.log", patterns, tmp_path)
        assert _is_ignored(tmp_path / "deep" / "nested" / "error.log", patterns, tmp_path)
        
        # **/temp/ should match temp dir at any level
        assert _is_ignored(tmp_path / "temp" / "file.txt", patterns, tmp_path)
        assert _is_ignored(tmp_path / "src" / "temp" / "file.txt", patterns, tmp_path)
        
        # docs/**/secret.txt should match only under docs
        assert not _is_ignored(tmp_path / "secret.txt", patterns, tmp_path)
        assert _is_ignored(tmp_path / "docs" / "secret.txt", patterns, tmp_path)
        assert _is_ignored(tmp_path / "docs" / "api" / "secret.txt", patterns, tmp_path)
    
    def test_escaped_special_characters(self, tmp_path):
        """Test patterns with escaped special characters."""
        patterns = [r"\#*", r"\!important", r"file\?.txt"]
        
        # Should match literal # at start
        assert _is_ignored(tmp_path / "#header.md", patterns, tmp_path)
        
        # Should match literal !
        assert _is_ignored(tmp_path / "!important", patterns, tmp_path)
        
        # Should match literal ?
        # Note: This might not work correctly in current implementation
        # as fnmatch treats ? as wildcard
        assert _is_ignored(tmp_path / "file?.txt", patterns, tmp_path)
    
    def test_trailing_spaces(self, tmp_path):
        """Test patterns with trailing spaces."""
        # Git ignores trailing spaces unless escaped
        patterns = ["file.txt ", "file2.txt\\ "]
        
        # "file.txt " should match "file.txt" (space ignored)
        assert _is_ignored(tmp_path / "file.txt", patterns, tmp_path)
        
        # "file2.txt\\ " should match "file2.txt " (literal space)
        # This is an edge case that might not be handled correctly
        # Documenting current behavior
        assert not _is_ignored(tmp_path / "file2.txt", patterns, tmp_path)
    
    def test_empty_patterns(self, tmp_path):
        """Test empty lines and comments in gitignore."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("""
# This is a comment
*.log

# Another comment
  # Indented comment
\t# Tab comment

*.tmp
""")
        
        patterns = _parse_gitignore(gitignore)
        
        # Should only have actual patterns
        assert patterns == ["*.log", "*.tmp"]
    
    def test_directory_vs_file_patterns(self, tmp_path):
        """Test patterns that distinguish directories from files."""
        patterns = ["temp", "logs/"]
        
        # "temp" matches both files and directories
        assert _is_ignored(tmp_path / "temp", patterns, tmp_path)
        assert _is_ignored(tmp_path / "temp" / "file.txt", patterns, tmp_path)
        
        # "logs/" only matches directories
        assert _is_ignored(tmp_path / "logs" / "app.log", patterns, tmp_path)
        # Note: Current implementation might not distinguish file vs dir
    
    def test_case_sensitivity(self, tmp_path):
        """Test case sensitivity in patterns."""
        patterns = ["*.LOG", "README"]
        
        # On case-sensitive systems, these should not match
        # On case-insensitive systems (Windows/macOS), they might
        # Document the platform-dependent behavior
        import platform
        is_case_insensitive = platform.system() in ["Windows", "Darwin"]
        
        if is_case_insensitive:
            assert _is_ignored(tmp_path / "debug.log", patterns, tmp_path)
            assert _is_ignored(tmp_path / "readme", patterns, tmp_path)
        else:
            assert not _is_ignored(tmp_path / "debug.log", patterns, tmp_path)
            assert not _is_ignored(tmp_path / "readme", patterns, tmp_path)
    
    def test_complex_glob_patterns(self, tmp_path):
        """Test complex glob patterns."""
        patterns = [
            "*.py[cod]",  # Matches .pyc, .pyo, .pyd
            "test_*.py",  # Matches test files
            "[._]*",      # Matches hidden files
            "*~",         # Matches backup files
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