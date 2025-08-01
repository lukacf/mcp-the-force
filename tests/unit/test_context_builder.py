"""Test context builder with stable list functionality."""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock

from mcp_the_force.utils.context_builder import (
    sort_files_for_stable_list,
    build_context_with_stable_list,
)
from mcp_the_force.utils.stable_list_cache import StableListCache


class TestDeterministicSorting:
    """Test deterministic file sorting for stable lists."""

    def test_sort_files_for_stable_list_basic(self):
        """Test basic sorting by token count then path."""
        # Mock file system calls
        file_info = {
            "/api/large.py": (10000, 2500),  # size, tokens
            "/api/small.py": (1000, 250),
            "/lib/medium.py": (5000, 1250),
            "/lib/tiny.py": (500, 125),
        }

        def mock_count_tokens_from_file(path):
            # Return the pre-calculated tokens for this path
            return file_info[path][1]

        with patch(
            "mcp_the_force.utils.context_builder.count_tokens_from_file",
            side_effect=mock_count_tokens_from_file,
        ):
            sorted_files = sort_files_for_stable_list(list(file_info.keys()))

        # Should be sorted by tokens (ascending) then path
        expected = [
            "/lib/tiny.py",  # 125 tokens
            "/api/small.py",  # 250 tokens
            "/lib/medium.py",  # 1250 tokens
            "/api/large.py",  # 2500 tokens
        ]
        assert sorted_files == expected

    def test_sort_files_with_same_token_count(self):
        """Test that files with same token count are sorted by path."""
        file_info = {
            "/z_file.py": (1000, 250),
            "/a_file.py": (1000, 250),
            "/m_file.py": (1000, 250),
        }

        def mock_count_tokens_from_file(path):
            return 250  # All have same tokens

        with patch(
            "mcp_the_force.utils.context_builder.count_tokens_from_file",
            side_effect=mock_count_tokens_from_file,
        ):
            sorted_files = sort_files_for_stable_list(list(file_info.keys()))

        # Should be sorted alphabetically when tokens are equal
        expected = ["/a_file.py", "/m_file.py", "/z_file.py"]
        assert sorted_files == expected

    def test_sort_files_with_missing_files(self):
        """Test that missing files are skipped."""
        files = [
            "/exists.py",
            "/missing.py",
            "/also_exists.py",
        ]

        def mock_count_tokens_from_file(path):
            if path == "/missing.py":
                raise FileNotFoundError()
            return 250

        with patch(
            "mcp_the_force.utils.context_builder.count_tokens_from_file",
            side_effect=mock_count_tokens_from_file,
        ):
            sorted_files = sort_files_for_stable_list(files)

        # Missing file should be skipped
        assert "/missing.py" not in sorted_files
        assert len(sorted_files) == 2


class TestBuildContextWithStableList:
    """Test the main context building algorithm."""

    @pytest.mark.asyncio
    async def test_first_call_creates_stable_list(self):
        """Test that first call with overflow creates and saves stable list."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name

        try:
            cache = StableListCache(db_path=db_path, ttl=3600)

            # Mock file system
            files = {
                "/api/file1.py": ("content1", 100),
                "/api/file2.py": ("content2", 150),
                "/api/file3.py": ("content3", 200),
                "/api/file4.py": ("content4", 300),  # This will overflow
            }

            def mock_gather_files(paths):
                return list(files.keys())

            def mock_load_files(paths):
                return [(p, files[p][0], files[p][1]) for p in paths if p in files]

            def mock_getsize(path):
                # Return size that corresponds to token count
                if path in files:
                    return files[path][1] * 4  # 4 bytes per token estimate
                raise FileNotFoundError()

            with patch(
                "mcp_the_force.utils.context_builder.gather_file_paths_async",
                side_effect=mock_gather_files,
            ):
                with patch(
                    "mcp_the_force.utils.context_builder.load_specific_files_async",
                    side_effect=mock_load_files,
                ):
                    # Mock count_tokens_from_file to return predictable values
                    def mock_count_tokens_from_file(path):
                        # Return token counts that match our expected logic
                        token_map = {
                            "/api/file1.py": 100,  # 25% of 400 token budget
                            "/api/file2.py": 150,  # 37.5% of budget
                            "/api/file3.py": 200,  # 50% of budget
                            "/api/file4.py": 300,  # 75% of budget - would overflow
                        }
                        return token_map.get(path, 100)

                    with patch(
                        "mcp_the_force.utils.context_builder.count_tokens_from_file",
                        side_effect=mock_count_tokens_from_file,
                    ):
                        (
                            inline_files,
                            overflow_files,
                            file_tree,
                        ) = await build_context_with_stable_list(
                            context_paths=["/api"],
                            session_id="test_session",
                            cache=cache,
                            token_budget=500,  # Only 3 files fit
                        )

            # Check results
            assert len(inline_files) == 3
            assert len(overflow_files) == 1
            assert "/api/file4.py" in overflow_files

            # Check stable list was saved
            saved_list = await cache.get_stable_list("test_session")
            # Stable list only contains paths, not full tuples
            assert saved_list == [item[0] for item in inline_files]

            cache.close()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_subsequent_call_no_changes(self):
        """Test that subsequent call with no changes sends no files."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name

        try:
            cache = StableListCache(db_path=db_path, ttl=3600)

            # First save a stable list
            stable_files = ["/api/file1.py", "/api/file2.py", "/api/file3.py"]
            await cache.save_stable_list("test_session", stable_files)

            # Save sent file info
            for file in stable_files:
                await cache.update_sent_file_info(
                    "test_session", file, 1000, 1700000000
                )

            # Mock file system - files haven't changed
            mock_stat = MagicMock()
            mock_stat.st_size = 1000
            mock_stat.st_mtime = 1700000000

            files = {
                "/api/file1.py": ("content1", 100),
                "/api/file2.py": ("content2", 150),
                "/api/file3.py": ("content3", 200),
                "/api/file4.py": ("content4", 300),
            }

            def mock_gather_files(paths):
                return list(files.keys())

            with patch("os.stat", return_value=mock_stat):
                with patch(
                    "mcp_the_force.utils.context_builder.gather_file_paths_async",
                    side_effect=mock_gather_files,
                ):
                    with patch(
                        "mcp_the_force.utils.context_loader.gather_file_paths",
                        side_effect=mock_gather_files,
                    ):
                        (
                            inline_files,
                            overflow_files,
                            file_tree,
                        ) = await build_context_with_stable_list(
                            context_paths=["/api"],
                            session_id="test_session",
                            cache=cache,
                            token_budget=500,
                        )

            # No files should be sent inline (none changed)
            assert len(inline_files) == 0
            # file4 should still be in overflow
            assert "/api/file4.py" in overflow_files

            cache.close()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_subsequent_call_with_changed_file(self):
        """Test that only changed files are sent on subsequent calls."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name

        try:
            cache = StableListCache(db_path=db_path, ttl=3600)

            # First save a stable list
            stable_files = ["/api/file1.py", "/api/file2.py", "/api/file3.py"]
            await cache.save_stable_list("test_session", stable_files)

            # Save sent file info (using nanosecond precision)
            await cache.update_sent_file_info(
                "test_session", "/api/file1.py", 1000, 1700000000000000000
            )
            await cache.update_sent_file_info(
                "test_session", "/api/file2.py", 1000, 1700000000000000000
            )
            await cache.update_sent_file_info(
                "test_session", "/api/file3.py", 1000, 1700000000000000000
            )

            # Mock file system - file2 has changed
            def mock_stat(path, **kwargs):
                stat = MagicMock()
                if path == "/api/file2.py":
                    stat.st_size = 1500  # Changed size
                    stat.st_mtime = 1700001000
                    stat.st_mtime_ns = 1700001000000000000  # Changed mtime_ns
                else:
                    stat.st_size = 1000
                    stat.st_mtime = 1700000000
                    stat.st_mtime_ns = 1700000000000000000  # Unchanged mtime_ns
                return stat

            files = {
                "/api/file1.py": ("content1", 100),
                "/api/file2.py": ("new content2", 150),
                "/api/file3.py": ("content3", 200),
                "/api/file4.py": ("content4", 300),
            }

            def mock_gather_files(paths):
                return list(files.keys())

            def mock_load_files(paths):
                return [(p, files[p][0], files[p][1]) for p in paths if p in files]

            with patch("os.stat", side_effect=mock_stat):
                with patch(
                    "mcp_the_force.utils.context_builder.gather_file_paths_async",
                    side_effect=mock_gather_files,
                ):
                    with patch(
                        "mcp_the_force.utils.context_builder.load_specific_files_async",
                        side_effect=mock_load_files,
                    ):
                        (
                            inline_files,
                            overflow_files,
                            file_tree,
                        ) = await build_context_with_stable_list(
                            context_paths=["/api"],
                            session_id="test_session",
                            cache=cache,
                            token_budget=500,
                        )

            # Only file2 should be sent
            assert len(inline_files) == 1
            assert inline_files[0][0] == "/api/file2.py"
            assert inline_files[0][1] == "new content2"

            # file4 should still be in overflow
            assert "/api/file4.py" in overflow_files

            cache.close()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_context_without_overflow(self):
        """Test that no stable list is created when context fits."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name

        try:
            cache = StableListCache(db_path=db_path, ttl=3600)

            # Small files that fit in budget
            files = {
                "/api/file1.py": ("content1", 100),
                "/api/file2.py": ("content2", 150),
            }

            def mock_gather_files(paths):
                return list(files.keys())

            def mock_load_files(paths):
                return [(p, files[p][0], files[p][1]) for p in paths if p in files]

            def mock_getsize(path):
                if path in files:
                    return files[path][1] * 4  # 4 bytes per token estimate
                raise FileNotFoundError()

            with patch(
                "mcp_the_force.utils.context_builder.gather_file_paths_async",
                side_effect=mock_gather_files,
            ):
                with patch(
                    "mcp_the_force.utils.context_builder.load_specific_files_async",
                    side_effect=mock_load_files,
                ):
                    # Mock count_tokens_from_file to return predictable values
                    def mock_count_tokens_from_file(path):
                        # Return token counts that match our expected logic
                        token_map = {
                            "/api/file1.py": 100,  # 25% of 400 token budget
                            "/api/file2.py": 150,  # 37.5% of budget
                            "/api/file3.py": 200,  # 50% of budget
                            "/api/file4.py": 300,  # 75% of budget - would overflow
                        }
                        return token_map.get(path, 100)

                    with patch(
                        "mcp_the_force.utils.context_builder.count_tokens_from_file",
                        side_effect=mock_count_tokens_from_file,
                    ):
                        (
                            inline_files,
                            overflow_files,
                            file_tree,
                        ) = await build_context_with_stable_list(
                            context_paths=["/api"],
                            session_id="test_session",
                            cache=cache,
                            token_budget=500,  # Everything fits
                        )

            # All files should be inline
            assert len(inline_files) == 2
            assert len(overflow_files) == 0

            cache.close()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Needs adjustment for tiktoken-based approach")
    async def test_priority_context_always_inline(self):
        """Test that priority_context files always go inline even on subsequent calls."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name

        try:
            cache = StableListCache(db_path=db_path, ttl=3600)

            def mock_stat(path):
                stat = MagicMock()
                # Tokens directly mapped in mock_count_tokens_from_file
                if path == "/api/file1.py":
                    stat.st_size = 200  # 100 tokens
                elif path == "/api/file2.py":
                    stat.st_size = 300  # 150 tokens
                elif path == "/api/file3.py":
                    stat.st_size = 400  # 200 tokens
                elif path == "/api/file4.py":
                    stat.st_size = 600  # 300 tokens
                elif path == "/api/priority.py":
                    stat.st_size = 150  # 75 tokens
                stat.st_mtime = 1700000000
                stat.st_mtime_ns = 1700000000000000000
                return stat

            files = {
                "/api/file1.py": ("content1", 100),
                "/api/file2.py": ("content2", 150),
                "/api/file3.py": ("content3", 200),
                "/api/file4.py": ("content4", 300),
                "/api/priority.py": ("priority content", 75),
            }

            def mock_gather_files(paths):
                if paths == ["/api"]:
                    return [
                        "/api/file1.py",
                        "/api/file2.py",
                        "/api/file3.py",
                        "/api/file4.py",
                    ]
                elif paths == ["/api/priority.py"]:
                    return ["/api/priority.py"]
                return []

            def mock_load_files(paths):
                return [(p, files[p][0], files[p][1]) for p in paths if p in files]

            with patch("os.stat", side_effect=mock_stat):
                with patch(
                    "os.path.getsize", side_effect=lambda p: mock_stat(p).st_size
                ):
                    with patch(
                        "mcp_the_force.utils.context_builder.gather_file_paths_async",
                        side_effect=mock_gather_files,
                    ):
                        with patch(
                            "mcp_the_force.utils.context_builder.load_specific_files_async",
                            side_effect=mock_load_files,
                        ):
                            # First call without priority context
                            (
                                inline_files,
                                overflow_files,
                                _,
                            ) = await build_context_with_stable_list(
                                context_paths=["/api"],
                                session_id="test_session",
                                cache=cache,
                                token_budget=500,
                            )

                            # file1, file2, file3 should be inline (total 450 tokens)
                            assert len(inline_files) == 3
                            assert "/api/file4.py" in overflow_files

                            # Second call WITH priority context
                            (
                                inline_files,
                                overflow_files,
                                _,
                            ) = await build_context_with_stable_list(
                                context_paths=["/api"],
                                session_id="test_session",
                                cache=cache,
                                token_budget=500,
                                priority_context=["/api/priority.py"],
                            )

                            # priority.py should be sent inline even though it wasn't in stable list
                            assert len(inline_files) == 1  # Only priority.py (new file)
                            assert inline_files[0][0] == "/api/priority.py"
                            assert (
                                "/api/file4.py" in overflow_files
                            )  # Still in overflow

            cache.close()
        finally:
            os.unlink(db_path)
