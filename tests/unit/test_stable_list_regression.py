"""Regression tests for stable list functionality."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mcp_the_force.utils.context_builder import build_context_with_stable_list
from mcp_the_force.utils.stable_list_cache import StableListCache


@pytest.fixture
async def temp_files():
    """Create temporary files for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        files = []
        # Create small files that will all fit inline
        for i in range(3):
            filepath = Path(tmpdir) / f"file{i}.txt"
            content = f"This is test file {i}\n" * 10  # Small file
            filepath.write_text(content)
            files.append(str(filepath))
        yield files


@pytest.fixture
async def mock_cache():
    """Create a mock StableListCache."""
    cache = AsyncMock(spec=StableListCache)
    cache.get_stable_list = AsyncMock(return_value=None)  # First call
    cache.save_stable_list = AsyncMock()
    cache.update_sent_file_info = AsyncMock()
    cache.batch_update_sent_files = AsyncMock()
    cache.file_changed_since_last_send = AsyncMock(return_value=True)
    return cache


class TestStableListRegression:
    """Regression tests for stable list bug where list wasn't saved when all files fit inline."""

    async def test_stable_list_saved_when_all_files_fit_inline(
        self, temp_files, mock_cache
    ):
        """Test that stable list is saved even when there's no overflow.

        This is a regression test for the bug where stable list was only saved
        when files overflowed to vector store, causing the entire codebase to
        be re-sent on every call.
        """
        # Setup
        session_id = "test-session"
        token_budget = 100_000  # Large budget so all files fit

        # First call - should save stable list
        files_sent, overflow_files, file_tree = await build_context_with_stable_list(
            context_paths=temp_files,
            session_id=session_id,
            cache=mock_cache,
            token_budget=token_budget,
            priority_context=None,
        )

        # Verify stable list was saved (this was the bug - it wasn't saved)
        mock_cache.save_stable_list.assert_called_once()
        call_args = mock_cache.save_stable_list.call_args
        assert call_args[0][0] == session_id  # First arg is session_id
        assert isinstance(call_args[0][1], list)  # Second arg is inline_paths list
        assert len(call_args[0][1]) == 3  # All 3 files should be in stable list

        # Verify files were sent
        assert len(files_sent) == 3
        assert len(overflow_files) == 0  # No overflow

        # Verify sent file info was updated
        assert mock_cache.batch_update_sent_files.called

    async def test_stable_list_prevents_resending_unchanged_files(
        self, temp_files, mock_cache
    ):
        """Test that subsequent calls only send changed files."""
        session_id = "test-session"
        token_budget = 100_000

        # Setup for second call - stable list exists
        mock_cache.get_stable_list = AsyncMock(return_value=temp_files)
        mock_cache.file_changed_since_last_send = AsyncMock(
            return_value=False
        )  # No changes

        # Second call - should not resend unchanged files
        files_sent, overflow_files, file_tree = await build_context_with_stable_list(
            context_paths=temp_files,
            session_id=session_id,
            cache=mock_cache,
            token_budget=token_budget,
            priority_context=None,
        )

        # Verify no files were sent (none changed)
        assert len(files_sent) == 0
        assert len(overflow_files) == 0

        # Verify stable list was NOT saved again (it already exists)
        mock_cache.save_stable_list.assert_not_called()

    async def test_stable_list_sends_only_changed_files(self, temp_files, mock_cache):
        """Test that only changed files are sent on subsequent calls."""
        session_id = "test-session"
        token_budget = 100_000

        # Setup for second call - stable list exists, one file changed
        mock_cache.get_stable_list = AsyncMock(return_value=temp_files)

        # Mock that only the first file has changed
        async def file_changed_mock(sid, filepath):
            return filepath.endswith("file0.txt")

        mock_cache.file_changed_since_last_send = AsyncMock(
            side_effect=file_changed_mock
        )

        # Mock both gather_file_paths_async and load_specific_files_async
        with patch(
            "mcp_the_force.utils.context_builder.gather_file_paths_async"
        ) as mock_gather:
            mock_gather.return_value = temp_files

            with patch(
                "mcp_the_force.utils.context_builder.load_specific_files_async"
            ) as mock_load:
                # Return content for the changed file
                mock_load.return_value = [(temp_files[0], "Changed content", 10)]

                # Second call - should only send the changed file
                (
                    files_sent,
                    overflow_files,
                    file_tree,
                ) = await build_context_with_stable_list(
                    context_paths=temp_files,
                    session_id=session_id,
                    cache=mock_cache,
                    token_budget=token_budget,
                    priority_context=None,
                )

        # Verify only one file was sent
        assert len(files_sent) == 1
        assert files_sent[0][0] == temp_files[0]  # First file in the list
        assert len(overflow_files) == 0

    async def test_stable_list_saved_with_overflow(self, temp_files, mock_cache):
        """Test that stable list is saved when there IS overflow (original behavior)."""
        session_id = "test-session"
        token_budget = 50  # Very small budget to force overflow

        # First call - should save stable list even with overflow
        files_sent, overflow_files, file_tree = await build_context_with_stable_list(
            context_paths=temp_files,
            session_id=session_id,
            cache=mock_cache,
            token_budget=token_budget,
            priority_context=None,
        )

        # Verify stable list was saved
        mock_cache.save_stable_list.assert_called_once()

        # Verify we have overflow
        assert len(overflow_files) > 0
        assert len(files_sent) < 3  # Not all files fit inline

    async def test_priority_context_always_inline(self, temp_files, mock_cache):
        """Test that priority context files are always sent inline on subsequent calls."""
        session_id = "test-session"
        token_budget = 100_000

        # Setup for second call - stable list exists without priority file
        regular_files = temp_files[:2]
        priority_file = temp_files[2]

        mock_cache.get_stable_list = AsyncMock(return_value=regular_files)

        # Mock file_changed_since_last_send to return False for regular files (already sent)
        # and True for priority file (new)
        async def file_changed_mock(sid, filepath):
            return filepath == priority_file

        mock_cache.file_changed_since_last_send = AsyncMock(
            side_effect=file_changed_mock
        )

        # Mock both gather_file_paths_async and load_specific_files_async
        with patch(
            "mcp_the_force.utils.context_builder.gather_file_paths_async"
        ) as mock_gather:
            # First call for priority files, second for regular files
            mock_gather.side_effect = [[priority_file], regular_files]

            with patch(
                "mcp_the_force.utils.context_builder.load_specific_files_async"
            ) as mock_load:
                # Return content for the priority file
                mock_load.return_value = [(priority_file, "Priority content", 10)]

                # Second call with priority context
                (
                    files_sent,
                    overflow_files,
                    file_tree,
                ) = await build_context_with_stable_list(
                    context_paths=regular_files,
                    session_id=session_id,
                    cache=mock_cache,
                    token_budget=token_budget,
                    priority_context=[priority_file],
                )

        # Verify priority file was sent even though it wasn't in stable list
        assert len(files_sent) == 1
        assert files_sent[0][0] == priority_file
