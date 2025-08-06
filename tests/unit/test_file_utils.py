"""
Unit tests for file utilities including .gitignore handling and file filtering.
"""

import os
from pathlib import Path
import pytest
from mcp_the_force.utils.fs import (
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

    def test_large_file_rejection(self, tmp_path, monkeypatch):
        """Test that files over max_file_size are rejected."""
        from unittest.mock import patch, MagicMock

        # Mock settings with a specific max file size
        mock_settings = MagicMock()
        mock_settings.mcp.max_file_size = 1 * 1024 * 1024  # 1MB for testing

        large_file = tmp_path / "large.txt"
        large_file.write_text("x" * (1024 * 1024 + 1))  # 1MB + 1 byte

        with patch("mcp_the_force.utils.fs.get_settings", return_value=mock_settings):
            # Note: _is_text_file no longer checks size, so this should return True
            # The size check is now in gather_file_paths
            assert _is_text_file(large_file)

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
        from unittest.mock import patch, MagicMock

        monkeypatch.chdir(tmp_path)

        # Mock settings with a specific total size limit
        mock_settings = MagicMock()
        mock_settings.mcp.max_file_size = 50 * 1024 * 1024  # 50MB per file
        mock_settings.mcp.max_total_size = 10 * 1024 * 1024  # 10MB total for testing

        # Create many 300KB files (would be 60MB total if all gathered)
        for i in range(200):
            f = tmp_path / f"file{i}.txt"
            f.write_text("x" * 300_000)  # 300KB each

        with patch("mcp_the_force.utils.fs.get_settings", return_value=mock_settings):
            files = gather_file_paths([str(tmp_path)])

        # Should stop before gathering all files
        assert len(files) < 200

        # Calculate total size
        total_size = sum(Path(f).stat().st_size for f in files)
        # Allow exceeding by one file (300KB) since check happens before adding
        assert total_size <= mock_settings.mcp.max_total_size + 300_000

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

    @pytest.mark.skip(reason="Path traversal protection disabled for MCP server usage")
    def test_path_traversal_blocked(self, tmp_path, monkeypatch):
        """Paths escaping the project root should be rejected."""
        # Ensure CI_E2E is not set during this test
        monkeypatch.delenv("CI_E2E", raising=False)

        # Create a non-temp directory to test from
        real_dir = Path.home() / ".test_path_traversal"
        real_dir.mkdir(exist_ok=True)

        try:
            monkeypatch.chdir(real_dir)

            # Create file outside the directory
            outside = real_dir.parent / "test_outside.txt"
            outside.write_text("secret")

            try:
                files = gather_file_paths([str(outside)])
                assert files == []
            finally:
                outside.unlink(missing_ok=True)
        finally:
            import shutil

            shutil.rmtree(real_dir, ignore_errors=True)

    def test_safe_path_allowed(self, tmp_path, monkeypatch):
        """Paths inside the project root should be processed."""
        monkeypatch.chdir(tmp_path)

        inside = tmp_path / "inside.txt"
        inside.write_text("ok")

        files = gather_file_paths([str(inside)])

        assert [str(inside)] == files


class TestFileSizeLimits:
    """Regression tests for file size limit handling."""

    def test_large_text_file_accepted(self, tmp_path, monkeypatch):
        """Test that text files up to max_file_size are accepted (regression test for 628KB file bug)."""
        from unittest.mock import patch, MagicMock

        monkeypatch.chdir(tmp_path)

        # Create a mock settings with 50MB file size limit
        mock_settings = MagicMock()
        mock_settings.mcp.max_file_size = 50 * 1024 * 1024  # 50MB
        mock_settings.mcp.max_total_size = 200 * 1024 * 1024  # 200MB

        # Create a 628KB text file (the size that was failing)
        large_file = tmp_path / "large_log.txt"
        large_file.write_text("x" * (628 * 1024))  # 628KB

        with patch("mcp_the_force.utils.fs.get_settings", return_value=mock_settings):
            files = gather_file_paths([str(large_file)])

        # File should be included
        assert len(files) == 1
        assert str(large_file) in files

    def test_file_exceeding_max_size_rejected(self, tmp_path, monkeypatch):
        """Test that files exceeding max_file_size are rejected."""
        from unittest.mock import patch, MagicMock

        monkeypatch.chdir(tmp_path)

        # Create a mock settings with 1MB file size limit
        mock_settings = MagicMock()
        mock_settings.mcp.max_file_size = 1 * 1024 * 1024  # 1MB
        mock_settings.mcp.max_total_size = 200 * 1024 * 1024  # 200MB

        # Create a 2MB text file
        huge_file = tmp_path / "huge.txt"
        huge_file.write_text("x" * (2 * 1024 * 1024))  # 2MB

        with patch("mcp_the_force.utils.fs.get_settings", return_value=mock_settings):
            files = gather_file_paths([str(huge_file)])

        # File should be rejected
        assert len(files) == 0

    def test_total_size_limit_with_large_files(self, tmp_path, monkeypatch):
        """Test that total size limit works with configurable limits."""
        from unittest.mock import patch, MagicMock

        monkeypatch.chdir(tmp_path)

        # Create a mock settings with 5MB total size limit
        mock_settings = MagicMock()
        mock_settings.mcp.max_file_size = 2 * 1024 * 1024  # 2MB per file
        mock_settings.mcp.max_total_size = 5 * 1024 * 1024  # 5MB total

        # Create three 2MB files (6MB total)
        for i in range(3):
            f = tmp_path / f"file{i}.txt"
            f.write_text("x" * (2 * 1024 * 1024))  # 2MB each

        with patch("mcp_the_force.utils.fs.get_settings", return_value=mock_settings):
            files = gather_file_paths([str(tmp_path)])

        # Should include 2 or 3 files (check happens before adding, so might include one extra)
        assert len(files) in [2, 3]

        # Total size should not exceed limit by more than one file
        total_size = sum(Path(f).stat().st_size for f in files)
        assert total_size <= mock_settings.mcp.max_total_size + (2 * 1024 * 1024)

    def test_context_paths_with_skip_safety_check(self, tmp_path, monkeypatch):
        """Test that context paths can use skip_safety_check for files outside project."""
        from unittest.mock import patch, MagicMock

        # Use a different directory as "project root"
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)

        # Create a file outside the project
        external_file = tmp_path / "external" / "data.txt"
        external_file.parent.mkdir()
        external_file.write_text("external data")

        mock_settings = MagicMock()
        mock_settings.mcp.max_file_size = 50 * 1024 * 1024
        mock_settings.mcp.max_total_size = 200 * 1024 * 1024
        mock_settings.security.path_blacklist = ["/etc", "/usr", "/bin"]

        with patch("mcp_the_force.utils.fs.get_settings", return_value=mock_settings):
            # Without skip_safety_check, should be rejected (if safety check was enforced)
            # But with skip_safety_check=True, should be accepted
            files = gather_file_paths([str(external_file)], skip_safety_check=True)

        assert len(files) == 1
        assert str(external_file) in files

    def test_optimizer_integration(self, tmp_path, monkeypatch):
        """Test that large files work correctly with TokenBudgetOptimizer."""
        import asyncio
        from mcp_the_force.optimization.token_budget_optimizer import (
            TokenBudgetOptimizer,
        )
        from unittest.mock import patch, MagicMock, AsyncMock

        monkeypatch.chdir(tmp_path)

        # Create a 628KB text file
        large_file = tmp_path / "large_log.txt"
        large_file.write_text("x" * (628 * 1024))

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.mcp.max_file_size = 50 * 1024 * 1024
        mock_settings.mcp.max_total_size = 200 * 1024 * 1024
        mock_settings.security.path_blacklist = []

        # Create optimizer with the file
        optimizer = TokenBudgetOptimizer(
            model_limit=200000,  # 200k context
            fixed_reserve=30000,
            session_id="test-session",
            context_paths=[str(large_file)],
            priority_paths=[],
            developer_prompt="Test prompt",
            instructions="Test instructions",
            output_format="Test output",
            project_name="test-project",
            tool_name="test-tool",
        )

        with patch("mcp_the_force.utils.fs.get_settings", return_value=mock_settings):
            # Mock the async parts
            mock_cache = AsyncMock()
            mock_cache.get_previous_inline_list.return_value = []
            mock_cache.is_first_call.return_value = True
            mock_cache.file_changed_since_last_send.return_value = True
            mock_cache.save_stable_list.return_value = None
            mock_cache.get_file_change_status.return_value = ([str(large_file)], [])

            with patch(
                "mcp_the_force.optimization.token_budget_optimizer.StableListCache",
                return_value=mock_cache,
            ):
                with patch(
                    "mcp_the_force.unified_session_cache.UnifiedSessionCache"
                ) as mock_session:
                    mock_session.return_value.get.return_value = None

                    # Run optimization
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        plan = loop.run_until_complete(optimizer.optimize())
                    finally:
                        loop.close()

                    # The file should be included in the plan
                    assert len(plan.inline_files) > 0 or len(plan.overflow_files) > 0
