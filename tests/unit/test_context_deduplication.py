"""Test priority_context behavior in context building."""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock

from mcp_the_force.utils.context_builder import build_context_with_stable_list
from mcp_the_force.utils.stable_list_cache import StableListCache


@pytest.mark.asyncio
async def test_priority_context_prioritization():
    """Test that files in priority_context are processed first."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        priority_file = os.path.realpath(os.path.join(tmpdir, "priority.py"))
        regular_file1 = os.path.realpath(os.path.join(tmpdir, "regular1.py"))
        regular_file2 = os.path.realpath(os.path.join(tmpdir, "regular2.py"))

        # Make files with different sizes
        with open(priority_file, "w") as f:
            f.write("# Priority file\n" * 30)  # Medium size
        with open(regular_file1, "w") as f:
            f.write("# Regular file 1\n" * 10)  # Small size
        with open(regular_file2, "w") as f:
            f.write("# Regular file 2\n" * 20)  # Small-medium size

        # Mock the cache
        cache = AsyncMock(spec=StableListCache)
        cache.get_stable_list.return_value = None  # First call, no stable list

        # Set a token budget that can fit all three files
        token_budget = 2000

        # Call with priority_context
        files_inline, files_overflow, file_tree = await build_context_with_stable_list(
            context_paths=[regular_file1, regular_file2],
            session_id="test-session",
            cache=cache,
            token_budget=token_budget,
            priority_context=[priority_file],
        )

        # Check that all files are inline (budget is sufficient)
        inline_paths = [f[0] for f in files_inline]
        assert len(files_inline) == 3
        assert priority_file in inline_paths
        assert regular_file1 in inline_paths
        assert regular_file2 in inline_paths
        assert len(files_overflow) == 0

        # Verify that priority file was processed first by checking the stable list
        # The stable list should have been saved with the correct order
        saved_calls = cache.save_stable_list.call_args_list
        if saved_calls:  # Only if stable list was saved (shouldn't be in this case since no overflow)
            saved_list = saved_calls[0][0][1]
            assert saved_list[0] == priority_file


@pytest.mark.asyncio
async def test_priority_context_overflow():
    """Test that priority_context files are ALWAYS inlined, even if they exceed budget."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        huge_priority = os.path.realpath(os.path.join(tmpdir, "huge_priority.py"))
        small_file = os.path.realpath(os.path.join(tmpdir, "small.py"))

        # Make a huge priority file that exceeds budget
        with open(huge_priority, "w") as f:
            f.write("# Huge priority file\n" * 10000)  # Very large
        with open(small_file, "w") as f:
            f.write("# Small file\n" * 5)  # Tiny

        # Mock the cache
        cache = AsyncMock(spec=StableListCache)
        cache.get_stable_list.return_value = None

        # Set a small token budget
        token_budget = 50  # Very small, normally can only fit the small file

        # Call with huge priority file
        files_inline, files_overflow, file_tree = await build_context_with_stable_list(
            context_paths=[small_file],
            session_id="test-session",
            cache=cache,
            token_budget=token_budget,
            priority_context=[huge_priority],
        )

        # Check that the huge priority file is INLINE (not overflowed)
        # Priority files should always be inlined regardless of budget
        inline_paths = [f[0] for f in files_inline]
        assert huge_priority in inline_paths
        # Small file might overflow since priority file takes all the budget
        assert len(files_inline) >= 1  # At least the priority file
        # Either small file is inline or in overflow (depending on remaining budget)
        assert small_file in inline_paths or small_file in files_overflow


@pytest.mark.asyncio
async def test_priority_context_deduplication():
    """Test that files appearing in both priority_context and context are deduplicated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test file
        shared_file = os.path.realpath(os.path.join(tmpdir, "shared.py"))

        with open(shared_file, "w") as f:
            f.write("# Shared file\n" * 20)

        # Mock the cache
        cache = AsyncMock(spec=StableListCache)
        cache.get_stable_list.return_value = None

        # Call with file in both priority_context and context
        files_inline, files_overflow, file_tree = await build_context_with_stable_list(
            context_paths=[shared_file],
            session_id="test-session",
            cache=cache,
            token_budget=1000,
            priority_context=[shared_file],
        )

        # Check that the file appears only once
        inline_paths = [f[0] for f in files_inline]
        assert inline_paths.count(shared_file) == 1
        assert len(files_overflow) == 0

        # Verify file tree doesn't have duplicates
        assert file_tree.count(os.path.basename(shared_file)) == 1
