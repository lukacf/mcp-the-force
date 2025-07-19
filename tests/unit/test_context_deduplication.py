"""Test context deduplication fix."""

import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock

from mcp_second_brain.utils.context_builder import build_context_with_stable_list
from mcp_second_brain.utils.stable_list_cache import StableListCache


@pytest.mark.asyncio
async def test_context_deduplication():
    """Test that files aren't duplicated when they appear in both context and attachments."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files (resolve symlinks for consistent paths)
        file1 = os.path.realpath(os.path.join(tmpdir, "file1.py"))
        file2 = os.path.realpath(os.path.join(tmpdir, "file2.py"))
        file3 = os.path.realpath(os.path.join(tmpdir, "file3.py"))

        # Small files that will fit inline
        with open(file1, "w") as f:
            f.write("# Small file 1\n")
        with open(file2, "w") as f:
            f.write("# Small file 2\n")

        # Large file that will overflow
        with open(file3, "w") as f:
            f.write("# Large file\n" * 10000)  # Make it large enough to overflow

        # Mock the cache
        cache = AsyncMock(spec=StableListCache)
        cache.get_stable_list.return_value = None  # First call, no stable list

        # Set a small token budget so file3 overflows
        token_budget = 100  # Very small budget

        # Call with file3 in both context and attachments
        files_inline, files_overflow, file_tree = await build_context_with_stable_list(
            context_paths=[os.path.realpath(tmpdir)],  # This will include all 3 files
            session_id="test-session",
            cache=cache,
            token_budget=token_budget,
            attachments=[file3],  # Also explicitly attach file3
        )

        # Check that file3 appears only once in overflow
        assert (
            files_overflow.count(file3) == 1
        ), f"file3 duplicated in overflow: {files_overflow}"

        # Check that the total unique files is correct
        all_files = set([f[0] for f in files_inline] + files_overflow)
        assert len(all_files) == 3, f"Expected 3 unique files, got {len(all_files)}"

        # Verify the specific files
        inline_paths = [f[0] for f in files_inline]
        assert file1 in inline_paths or file1 in files_overflow
        assert file2 in inline_paths or file2 in files_overflow
        assert file3 in files_overflow  # Should be in overflow due to size

        # Verify file tree doesn't have duplicates
        # The tree should mention each file exactly once
        assert file_tree.count(os.path.basename(file1)) == 1
        assert file_tree.count(os.path.basename(file2)) == 1
        assert file_tree.count(os.path.basename(file3)) == 1


@pytest.mark.asyncio
async def test_attachment_deduplication_logging():
    """Test that deduplication is properly logged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files (resolve symlinks for consistent paths)
        file1 = os.path.realpath(os.path.join(tmpdir, "file1.py"))
        file2 = os.path.realpath(os.path.join(tmpdir, "file2.py"))

        with open(file1, "w") as f:
            f.write("# File 1\n" * 10000)  # Large file
        with open(file2, "w") as f:
            f.write("# File 2\n" * 10000)  # Large file

        # Mock the cache
        cache = AsyncMock(spec=StableListCache)
        cache.get_stable_list.return_value = None

        # Mock logger to capture log messages
        with patch("mcp_second_brain.utils.context_builder.logger") as mock_logger:
            # Call with overlapping files
            await build_context_with_stable_list(
                context_paths=[os.path.realpath(tmpdir)],  # Includes both files
                session_id="test-session",
                cache=cache,
                token_budget=50,  # Small budget so both overflow
                attachments=[file1, file2],  # Also attach both
            )

            # Check that deduplication was logged
            log_calls = [str(call) for call in mock_logger.info.call_args_list]
            dedup_log = None
            for call in log_calls:
                if "unique attachment files" in call and "skipped" in call:
                    dedup_log = call
                    break

            assert dedup_log is not None, "Deduplication not logged"
            assert (
                "skipped 2 duplicates" in dedup_log
            ), f"Expected 2 duplicates skipped, log: {dedup_log}"
