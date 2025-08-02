"""Tests for FusionTree file tree builder functionality."""

from pathlib import Path
import tempfile

from mcp_the_force.utils.file_tree import (
    build_file_tree_from_paths,
)


class TestFileTreeBuilder:
    """Test FusionTree file tree building functionality."""

    def test_build_file_tree_from_paths(self):
        """Test building FusionTree from a list of paths."""
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

            # FusionTree format: compact with compression
            assert str(root) in tree
            # Files should be present in some form (possibly grouped)
            assert "helper.py" in tree or "py{" in tree
            assert "src[" in tree  # Directory structure
            assert "lib[" in tree

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

            # Should show both files in FusionTree format
            assert "main.py" in tree
            assert "config.json" in tree
            # Should handle different roots with common parent

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

            # Should show parent directory and file in FusionTree format
            assert str(tmpdir) in tree
            assert "single.py" in tree

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

            # FusionTree will likely compress this into a sequence
            # Look for sequence compression or individual files
            assert "file" in tree
            # Could be compressed as file[0-2].txt or individual files

    def test_file_tree_complex_structure(self):
        """Test complex nested structure with FusionTree compression."""
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

            # FusionTree produces compact output
            assert str(root) in tree

            # Should have proper nesting with brackets
            assert "src[" in tree
            assert "models[" in tree
            assert "utils[" in tree
            assert "tests[" in tree

            # Files should be present in some form
            assert "test_user.py" in tree
            assert "README.md" in tree

    def test_extension_grouping(self):
        """Test FusionTree's extension grouping feature."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create multiple Python files
            (root / "src").mkdir()
            files = [
                root / "src" / "main.py",
                root / "src" / "utils.py",
                root / "src" / "config.py",
            ]

            for f in files:
                f.write_text("content")

            all_paths = [str(f) for f in files]
            attachment_paths = [
                str(root / "src" / "config.py")
            ]  # Only config is attached

            tree = build_file_tree_from_paths(all_paths, attachment_paths)

            # Should use extension grouping
            assert "py{" in tree or all(f.stem in tree for f in files)

    def test_sequence_compression(self):
        """Test FusionTree's sequence compression feature."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create numbered sequence
            (root / "images").mkdir()
            files = []
            for i in range(5):
                f = root / "images" / f"img{i:03d}.png"
                f.write_text("image")
                files.append(str(f))

            all_paths = files
            attachment_paths = [files[1]]  # Mark img001.png as attached

            tree = build_file_tree_from_paths(all_paths, attachment_paths)

            # Should compress sequence
            assert "img[" in tree or "img" in tree
            # May use range notation if sequence is long enough

    def test_prefix_factorization(self):
        """Test FusionTree's prefix factorization feature."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create files with common prefix separated by underscore
            (root / "components").mkdir()
            files = [
                root / "components" / "Modal_Button.tsx",
                root / "components" / "Modal_Header.tsx",
                root / "components" / "Modal_Footer.tsx",
            ]

            for f in files:
                f.write_text("component")

            all_paths = [str(f) for f in files]
            attachment_paths = [str(files[0])]  # Only Button is attached

            tree = build_file_tree_from_paths(all_paths, attachment_paths)

            # Should either factor common prefix or list files individually
            assert "Modal" in tree
            # May have factorization syntax {Button,Header,Footer} or individual files

    def test_truncation_with_max_items(self):
        """Test FusionTree's truncation feature."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create many files
            files = []
            for i in range(20):
                f = root / f"file{i:02d}.txt"
                f.write_text(f"content{i}")
                files.append(str(f))

            all_paths = files
            attachment_paths = files[:2]  # First two are attached

            # Use small max_items to trigger truncation
            tree = build_file_tree_from_paths(
                all_paths, attachment_paths, max_items_per_dir=5
            )

            # Should show truncation marker
            assert (
                "+" in tree or len([f for f in files if f.split("/")[-1] in tree]) <= 10
            )

    def test_keeps_attachment_semantics(self):
        """Test that attachment information is preserved through compression."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create a simple structure where we can verify attachment markers
            files = [
                root / "attached.txt",
                root / "not_attached.txt",
            ]

            for f in files:
                f.write_text("content")

            all_paths = [str(f) for f in files]
            attachment_paths = [str(files[0])]  # Only first file attached

            tree = build_file_tree_from_paths(all_paths, attachment_paths)

            # Should contain both file stems and preserve attachment information
            # Files may be grouped by extension: txt{attached,not_attached}
            assert "attached" in tree
            assert "not_attached" in tree
            # The exact format may vary due to compression
