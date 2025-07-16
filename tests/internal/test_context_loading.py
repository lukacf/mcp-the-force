"""
Integration tests for context loading with real file system operations.
"""

import os
import pytest
from mcp_second_brain.utils.fs import gather_file_paths
from mcp_second_brain.utils.prompt_builder import build_prompt


class TestContextLoadingIntegration:
    """Test file loading and context building with real file operations."""

    def test_complex_project_structure(self, tmp_path):
        """Test loading files from a complex project structure."""
        # Create a realistic project structure
        project = tmp_path / "myproject"
        project.mkdir()

        # Source files
        src = project / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "main.py").write_text(
            "from .utils import helper\n\ndef main():\n    helper()"
        )
        (src / "utils.py").write_text("def helper():\n    print('Helping!')")

        # Tests
        tests = project / "tests"
        tests.mkdir()
        (tests / "test_main.py").write_text("def test_main():\n    assert True")

        # Config files
        (project / "pyproject.toml").write_text("[project]\nname = 'myproject'")
        (project / "README.md").write_text("# My Project\n\nAwesome project!")

        # Create .gitignore
        (project / ".gitignore").write_text("__pycache__/\n*.pyc\n.pytest_cache/\n")

        # Add some ignored files
        (src / "__pycache__").mkdir()
        (src / "__pycache__" / "main.cpython-39.pyc").write_bytes(b"fake pyc")

        # Gather files
        files = gather_file_paths([str(project)])

        # Should include source and config files
        assert any("main.py" in f for f in files)
        assert any("utils.py" in f for f in files)
        assert any("test_main.py" in f for f in files)
        assert any("pyproject.toml" in f for f in files)
        assert any("README.md" in f for f in files)

        # Should not include ignored files
        assert not any("__pycache__" in f for f in files)
        assert not any(".pyc" in f for f in files)

        # Files should be sorted
        assert files == sorted(files)

    def test_symlink_handling(self, tmp_path):
        """Test handling of symbolic links."""
        # Create target files
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        (target_dir / "shared.py").write_text("# Shared code")

        # Create project with symlink
        project = tmp_path / "project"
        project.mkdir()
        (project / "main.py").write_text("import shared")

        # Create symlink
        symlink = project / "shared.py"
        symlink.symlink_to(target_dir / "shared.py")

        # Gather files
        files = gather_file_paths([str(project)])

        # Should include both files
        assert len(files) == 2
        assert any("main.py" in f for f in files)
        assert any("shared.py" in f for f in files)

    def test_permission_errors(self, tmp_path):
        """Test graceful handling of permission errors."""
        if os.name == "nt":
            pytest.skip("Permission test not reliable on Windows")

        # Create files with different permissions
        project = tmp_path / "project"
        project.mkdir()

        (project / "readable.py").write_text("# Can read this")

        secret = project / "secret.py"
        secret.write_text("# Can't read this")
        secret.chmod(0o000)

        try:
            # Gather files
            files = gather_file_paths([str(project)])

            # Should include readable file
            readable_files = [f for f in files if "readable.py" in f]
            assert len(readable_files) == 1

            # On some systems (macOS), files with 000 permissions might still
            # be listed but not readable. The important thing is that we can
            # gather files without crashing on permission errors.
        finally:
            # Restore permissions for cleanup
            secret.chmod(0o644)

    def test_encoding_handling(self, tmp_path):
        """Test handling of different file encodings."""
        # UTF-8 file
        utf8_file = tmp_path / "utf8.py"
        utf8_file.write_text("# UTF-8: Hello 世界", encoding="utf-8")

        # Latin-1 file
        latin1_file = tmp_path / "latin1.py"
        latin1_file.write_text("# Latin-1: café", encoding="latin-1")

        # ASCII file
        ascii_file = tmp_path / "ascii.py"
        ascii_file.write_text("# Plain ASCII", encoding="ascii")

        # Gather files
        files = gather_file_paths([str(tmp_path)])

        # All text files should be included
        assert len(files) == 3

    def test_prompt_building_with_real_files(self, temp_project):
        """Test building prompts with real file content."""
        # Build prompt with inline files
        prompt, attachments = build_prompt(
            "Analyze this code",  # instructions
            "markdown",  # output_format
            [str(temp_project)],  # context
        )

        # Should include instructions
        assert "Analyze this code" in prompt
        assert "markdown" in prompt

        # Should include file contents
        assert "main.py" in prompt
        assert "print('hello')" in prompt
        assert "utils.py" in prompt
        assert "def helper():" in prompt

        # Should not include ignored files
        assert "debug.log" not in prompt

    def test_token_limit_handling(self, tmp_path):
        """Test handling of files that exceed token limits."""
        # Create files that will exceed inline limit
        for i in range(20):
            large_file = tmp_path / f"large{i}.py"
            large_file.write_text("# Large file\n" + "x" * 5000)

        # Build prompt - should handle gracefully
        prompt, attachments = build_prompt(
            "Analyze",  # instructions
            "text",  # output_format
            [str(tmp_path)],  # context
        )

        # Should still have a valid prompt
        assert "Analyze" in prompt

        # With MAX_INLINE_TOKENS=12000, some files might be inlined
        # Check if we have attachments (files that exceeded inline limit)
        if attachments:
            assert "file search tool" in prompt
        else:
            # All files were inlined - prompt will be large
            assert len(prompt) > 10000

    def test_binary_file_filtering(self, tmp_path):
        """Test that binary files are properly filtered."""
        # Create mix of text and binary files
        (tmp_path / "code.py").write_text("print('hello')")
        (tmp_path / "doc.md").write_text("# Documentation")

        # Binary files
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (tmp_path / "data.bin").write_bytes(bytes(range(256)))

        # File with binary content but text extension
        (tmp_path / "bad.txt").write_bytes(b"\x00\x01\x02\x03")

        files = gather_file_paths([str(tmp_path)])

        # Should include text files (including .txt even with binary content)
        assert len(files) == 3
        assert any("code.py" in f for f in files)
        assert any("doc.md" in f for f in files)
        assert any("bad.txt" in f for f in files)  # .txt extension is trusted

        # Should not include files with binary extensions
        assert not any("image.png" in f for f in files)
        assert not any("data.bin" in f for f in files)

    def test_nested_gitignore(self, tmp_path):
        """Test handling of nested .gitignore files."""
        # Root .gitignore
        (tmp_path / ".gitignore").write_text("*.log\n")

        # Create subdirectory with its own .gitignore
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / ".gitignore").write_text("*.tmp\n")

        # Create files
        (tmp_path / "root.py").write_text("# Root")
        (tmp_path / "debug.log").write_text("Log")
        (subdir / "sub.py").write_text("# Sub")
        (subdir / "data.tmp").write_text("Temp")
        (subdir / "sub.log").write_text("Sub log")

        files = gather_file_paths([str(tmp_path)])

        # Should respect root .gitignore (current implementation only uses first .gitignore found)
        assert any("root.py" in f for f in files)
        assert any("sub.py" in f for f in files)
        assert not any("debug.log" in f for f in files)
        assert not any("sub.log" in f for f in files)  # *.log from root .gitignore

        # Note: Current implementation doesn't handle nested .gitignore files
        # so data.tmp will be included even though subdir/.gitignore excludes it
        assert any("data.tmp" in f for f in files)
