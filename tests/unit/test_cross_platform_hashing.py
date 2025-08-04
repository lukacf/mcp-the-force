"""Test cross-platform hashing consistency for deduplication systems.

These tests verify that the hashing functions produce consistent results
across different platforms (Windows, macOS, Linux) by handling different
line ending formats properly.
"""

import pytest
from mcp_the_force.dedup.hashing import compute_content_hash, compute_fileset_hash
from mcp_the_force.tools.search_dedup_sqlite import SQLiteSearchDeduplicator


class TestCrossPlatformHashingConsistency:
    """Test that hashing functions are deterministic across platforms."""

    def test_compute_content_hash_normalizes_line_endings(self):
        """Test that different line ending formats produce identical hashes."""
        # Same logical content with different line endings
        content_unix = "line one\nline two\nline three"
        content_windows = "line one\r\nline two\r\nline three"
        content_old_mac = "line one\rline two\rline three"
        content_mixed = (
            "line one\r\nline two\nline three"  # Mixed but same logical content
        )

        # All should produce the same hash after normalization
        hash_unix = compute_content_hash(content_unix)
        hash_windows = compute_content_hash(content_windows)
        hash_old_mac = compute_content_hash(content_old_mac)
        hash_mixed = compute_content_hash(content_mixed)

        assert (
            hash_unix == hash_windows
        ), "Unix and Windows line endings should produce same hash"
        assert (
            hash_unix == hash_old_mac
        ), "Unix and old Mac line endings should produce same hash"
        assert (
            hash_unix == hash_mixed
        ), "Mixed line endings should normalize to same hash"

        # Verify it's a proper SHA-256 hash
        assert len(hash_unix) == 64
        assert all(c in "0123456789abcdef" for c in hash_unix)

    def test_compute_fileset_hash_normalizes_line_endings(self):
        """Test that fileset hashing normalizes line endings for consistency."""
        # Same logical files with different line endings
        files_unix = [
            ("file1.py", "def hello():\n    print('Hello')\n"),
            ("file2.py", "def world():\n    print('World')\n"),
        ]

        files_windows = [
            ("file1.py", "def hello():\r\n    print('Hello')\r\n"),
            ("file2.py", "def world():\r\n    print('World')\r\n"),
        ]

        files_mixed = [
            ("file1.py", "def hello():\r\n    print('Hello')\n"),  # Mixed
            ("file2.py", "def world():\r    print('World')\r\n"),  # Mixed
        ]

        hash_unix = compute_fileset_hash(files_unix)
        hash_windows = compute_fileset_hash(files_windows)
        hash_mixed = compute_fileset_hash(files_mixed)

        assert (
            hash_unix == hash_windows
        ), "Fileset hash should be same for Unix vs Windows line endings"
        assert (
            hash_unix == hash_mixed
        ), "Fileset hash should be same for mixed line endings"

        # Verify it's a proper SHA-256 hash
        assert len(hash_unix) == 64

    def test_compute_fileset_hash_order_independence_with_line_endings(self):
        """Test that file order doesn't affect hash even with different line endings."""
        files_order1 = [
            ("a.py", "content A\nline 2"),
            ("b.py", "content B\r\nline 2"),
        ]

        files_order2 = [
            ("b.py", "content B\nline 2"),  # Same logical content, normalized endings
            ("a.py", "content A\r\nline 2"),  # Same logical content, different endings
        ]

        hash1 = compute_fileset_hash(files_order1)
        hash2 = compute_fileset_hash(files_order2)

        assert (
            hash1 == hash2
        ), "File order should not affect hash with different line endings"

    def test_search_deduplicator_cross_platform_consistency(self):
        """Test that search deduplication is consistent across platforms."""
        # Same logical content with different line endings
        content_unix = "Search result content\nSecond line"
        content_windows = "Search result content\r\nSecond line"
        content_old_mac = "Search result content\rSecond line"

        file_id = "test_file.txt"

        # All should produce the same hash
        hash_unix = SQLiteSearchDeduplicator.compute_content_hash_for_dedup(
            content_unix, file_id
        )
        hash_windows = SQLiteSearchDeduplicator.compute_content_hash_for_dedup(
            content_windows, file_id
        )
        hash_old_mac = SQLiteSearchDeduplicator.compute_content_hash_for_dedup(
            content_old_mac, file_id
        )

        assert (
            hash_unix == hash_windows
        ), "Search dedup should be consistent Unix vs Windows"
        assert (
            hash_unix == hash_old_mac
        ), "Search dedup should be consistent Unix vs old Mac"

        # Should be truncated to 16 characters (existing behavior)
        assert len(hash_unix) == 16

    def test_edge_cases_line_ending_normalization(self):
        """Test edge cases in line ending normalization."""
        # Empty string
        assert compute_content_hash("") == compute_content_hash("")

        # Only line endings
        assert compute_content_hash("\n") == compute_content_hash("\r\n")
        assert compute_content_hash("\n") == compute_content_hash("\r")

        # Multiple consecutive line endings
        content1 = "text\n\nmore text"
        content2 = "text\r\n\r\nmore text"
        content3 = "text\r\rmore text"

        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)
        hash3 = compute_content_hash(content3)

        assert hash1 == hash2, "Multiple consecutive line endings should normalize"
        assert hash1 == hash3, "Different multiple line endings should normalize"

        # Trailing line endings
        assert compute_content_hash("text\n") == compute_content_hash("text\r\n")
        assert compute_content_hash("text\n") == compute_content_hash("text\r")


class TestBackwardCompatibility:
    """Test that the fix maintains backward compatibility where possible."""

    def test_hash_lengths_preserved(self):
        """Test that hash lengths remain the same for existing systems."""
        content = "test content\nwith newlines"

        # Full content hash should be 64 characters (SHA-256 hex)
        full_hash = compute_content_hash(content)
        assert len(full_hash) == 64

        # Search dedup hash should be 16 characters (truncated)
        dedup_hash = SQLiteSearchDeduplicator.compute_content_hash_for_dedup(
            content, "file.txt"
        )
        assert len(dedup_hash) == 16

        # Truncated hash should be prefix of full hash
        combined_content = f"{content}:file.txt"
        full_combined_hash = compute_content_hash(combined_content)
        assert dedup_hash == full_combined_hash[:16]

    def test_utf8_encoding_consistency(self):
        """Test that UTF-8 encoding works consistently across platforms."""
        # Unicode content with different line endings
        unicode_content_unix = "Hello 世界\nUnicode test\n你好"
        unicode_content_windows = "Hello 世界\r\nUnicode test\r\n你好"

        hash_unix = compute_content_hash(unicode_content_unix)
        hash_windows = compute_content_hash(unicode_content_windows)

        assert hash_unix == hash_windows, "Unicode content should hash consistently"

        # Should work with search deduplication too
        dedup_hash_unix = SQLiteSearchDeduplicator.compute_content_hash_for_dedup(
            unicode_content_unix, "unicode.txt"
        )
        dedup_hash_windows = SQLiteSearchDeduplicator.compute_content_hash_for_dedup(
            unicode_content_windows, "unicode.txt"
        )

        assert (
            dedup_hash_unix == dedup_hash_windows
        ), "Unicode search dedup should be consistent"


class TestRegressionPrevention:
    """Test to prevent regression of the cross-platform issue."""

    def test_different_content_produces_different_hashes(self):
        """Ensure that truly different content still produces different hashes."""
        content1 = "First content\nwith some text"
        content2 = "Second content\nwith different text"

        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)

        assert hash1 != hash2, "Different content should produce different hashes"

        # Same for search deduplication
        dedup_hash1 = SQLiteSearchDeduplicator.compute_content_hash_for_dedup(
            content1, "file.txt"
        )
        dedup_hash2 = SQLiteSearchDeduplicator.compute_content_hash_for_dedup(
            content2, "file.txt"
        )

        assert (
            dedup_hash1 != dedup_hash2
        ), "Different content should produce different dedup hashes"

    def test_same_content_different_file_ids_produces_different_hashes(self):
        """Test that same content in different files produces different dedup hashes."""
        content = "Same content\nacross files"

        hash_file1 = SQLiteSearchDeduplicator.compute_content_hash_for_dedup(
            content, "file1.txt"
        )
        hash_file2 = SQLiteSearchDeduplicator.compute_content_hash_for_dedup(
            content, "file2.txt"
        )

        assert (
            hash_file1 != hash_file2
        ), "Same content in different files should have different hashes"

    def test_cross_platform_demo_scenario(self):
        """Demo the specific cross-platform scenario that was broken before the fix."""
        # Simulate a file that might be created on Windows but read on Unix
        python_code_windows = "def calculate_sum(a, b):\r\n    return a + b\r\n\r\nif __name__ == '__main__':\r\n    print(calculate_sum(1, 2))"
        python_code_unix = "def calculate_sum(a, b):\n    return a + b\n\nif __name__ == '__main__':\n    print(calculate_sum(1, 2))"

        # Before the fix, these would have different hashes
        # After the fix, they should have the same hash
        hash_windows = compute_content_hash(python_code_windows)
        hash_unix = compute_content_hash(python_code_unix)

        assert hash_windows == hash_unix, (
            "CRITICAL: Cross-platform line ending normalization failed! "
            "This will cause cache misses and inconsistent behavior across platforms."
        )

        # Verify in fileset context too
        fileset_windows = [("main.py", python_code_windows)]
        fileset_unix = [("main.py", python_code_unix)]

        fileset_hash_windows = compute_fileset_hash(fileset_windows)
        fileset_hash_unix = compute_fileset_hash(fileset_unix)

        assert fileset_hash_windows == fileset_hash_unix, (
            "CRITICAL: Cross-platform fileset hashing failed! "
            "This will cause vector store cache misses across platforms."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
