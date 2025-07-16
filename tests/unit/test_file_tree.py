"""Tests for file tree builder functionality."""

from pathlib import Path
import tempfile

from mcp_second_brain.utils.file_tree import (
    build_file_tree_from_paths,
)


class TestFileTreeBuilder:
    """Test file tree building functionality."""

    def test_build_file_tree_from_paths(self):
        """Test building file tree from a list of paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create files
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("app")
            (root / "src" / "config.py").write_text("config")
            (root / "lib").mkdir()
            (root / "lib" / "helper.py").write_text("helper")

            # List of all paths
            all_paths = [
                str(root / "src" / "app.py"),
                str(root / "src" / "config.py"),
                str(root / "lib" / "helper.py"),
            ]

            # Mark some as attached
            attachment_paths = [
                str(root / "src" / "config.py"),
                str(root / "lib" / "helper.py"),
            ]

            tree = build_file_tree_from_paths(all_paths, attachment_paths, root)

            lines = tree.split("\n")
            assert str(root) in lines[0]
            assert any("app.py" in line and "attached" not in line for line in lines)
            assert any("config.py attached" in line for line in lines)
            assert any("helper.py attached" in line for line in lines)

    def test_file_tree_with_files_from_different_locations(self):
        """Test building tree with files from completely different locations."""
        with (
            tempfile.TemporaryDirectory() as tmpdir1,
            tempfile.TemporaryDirectory() as tmpdir2,
        ):
            # Create files in different locations
            file1 = Path(tmpdir1) / "project1" / "main.py"
            file1.parent.mkdir(parents=True)
            file1.write_text("main")

            file2 = Path(tmpdir2) / "data" / "config.json"
            file2.parent.mkdir(parents=True)
            file2.write_text("{}")

            # All paths
            all_paths = [str(file1), str(file2)]

            # Mark one as attached
            attachment_paths = [str(file2)]

            tree = build_file_tree_from_paths(all_paths, attachment_paths)

            # Should show both files with proper markers
            assert "main.py" in tree
            assert "config.json attached" in tree

            # Should handle different roots gracefully
            lines = tree.split("\n")
            # Should have multiple root sections
            assert (
                len(
                    [
                        line
                        for line in lines
                        if line
                        and not line.startswith(" ")
                        and not line.startswith("│")
                        and not line.startswith("├")
                        and not line.startswith("└")
                    ]
                )
                >= 1
            )

    def test_file_tree_empty(self):
        """Test building tree with no files."""
        tree = build_file_tree_from_paths([], [])
        assert tree == "(empty)"

    def test_file_tree_single_file(self):
        """Test building tree with a single file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "single.py"
            file_path.write_text("content")

            tree = build_file_tree_from_paths([str(file_path)], [])

            # Should show parent directory and file
            assert str(tmpdir) in tree
            assert "single.py" in tree
            assert "attached" not in tree  # Not marked as attached

    def test_file_tree_all_attached(self):
        """Test when all files are attachments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            files = []
            for i in range(3):
                f = root / f"file{i}.txt"
                f.write_text(f"content{i}")
                files.append(str(f))

            # All files are attachments
            tree = build_file_tree_from_paths(files, files)

            # All should be marked as attached
            assert "file0.txt attached" in tree
            assert "file1.txt attached" in tree
            assert "file2.txt attached" in tree

    def test_file_tree_complex_structure(self):
        """Test complex nested structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create complex structure
            (root / "src" / "models").mkdir(parents=True)
            (root / "src" / "utils").mkdir()
            (root / "tests" / "unit").mkdir(parents=True)

            files = [
                root / "src" / "main.py",
                root / "src" / "models" / "user.py",
                root / "src" / "models" / "post.py",
                root / "src" / "utils" / "helpers.py",
                root / "tests" / "unit" / "test_user.py",
                root / "README.md",
            ]

            for f in files:
                f.write_text("content")

            all_paths = [str(f) for f in files]
            # Mark tests and README as attached
            attachment_paths = [
                str(root / "tests" / "unit" / "test_user.py"),
                str(root / "README.md"),
            ]

            tree = build_file_tree_from_paths(all_paths, attachment_paths)

            # Check structure
            lines = tree.split("\n")

            # Should have proper nesting
            assert any("src" in line for line in lines)
            assert any("models" in line for line in lines)
            assert any("utils" in line for line in lines)

            # Check attached markers
            assert any("test_user.py attached" in line for line in lines)
            assert any("README.md attached" in line for line in lines)

            # Check non-attached files
            assert any("main.py" in line and "attached" not in line for line in lines)
            assert any("user.py" in line and "attached" not in line for line in lines)
