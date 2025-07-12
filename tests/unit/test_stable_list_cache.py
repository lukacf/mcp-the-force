"""Test stable list cache for context overflow management."""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock

from mcp_second_brain.utils.stable_list_cache import StableListCache


@pytest.mark.asyncio
async def test_save_and_retrieve_stable_list():
    """Test saving and retrieving stable list."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        # Save a stable list
        file_paths = ["/api/file1.py", "/api/file2.py", "/lib/file3.py"]
        await cache.save_stable_list("test_session", file_paths)

        # Retrieve it
        result = await cache.get_stable_list("test_session")
        assert result == file_paths

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_retrieve_non_existent_list():
    """Test retrieving a non-existent stable list returns None."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        result = await cache.get_stable_list("nonexistent_session")
        assert result is None

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_overwrite_stable_list():
    """Test overwriting an existing stable list."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        # Save initial list
        initial_list = ["/api/file1.py", "/api/file2.py"]
        await cache.save_stable_list("test_session", initial_list)

        # Overwrite with new list
        new_list = ["/lib/file3.py", "/lib/file4.py", "/lib/file5.py"]
        await cache.save_stable_list("test_session", new_list)

        # Should get the new list
        result = await cache.get_stable_list("test_session")
        assert result == new_list

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_save_and_get_sent_file_info():
    """Test saving and retrieving sent file info."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        # Save file info
        await cache.update_sent_file_info(
            "test_session", "/api/file1.py", 12345, 1700000000
        )

        # Retrieve it
        result = await cache.get_sent_file_info("test_session", "/api/file1.py")
        assert result is not None
        assert result["size"] == 12345
        assert result["mtime"] == 1700000000

        # Non-existent file returns None
        result = await cache.get_sent_file_info("test_session", "/api/nonexistent.py")
        assert result is None

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_update_sent_file_info():
    """Test updating existing sent file info."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        # Save initial info
        await cache.update_sent_file_info(
            "test_session", "/api/file1.py", 12345, 1700000000
        )

        # Update with new info
        await cache.update_sent_file_info(
            "test_session", "/api/file1.py", 54321, 1700001000
        )

        # Should get updated info
        result = await cache.get_sent_file_info("test_session", "/api/file1.py")
        assert result["size"] == 54321
        assert result["mtime"] == 1700001000

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_batch_update_sent_files():
    """Test batch updating multiple files."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        # Batch update multiple files
        files_info = [
            ("/api/file1.py", 12345, 1700000000),
            ("/api/file2.py", 23456, 1700000100),
            ("/api/file3.py", 34567, 1700000200),
        ]
        await cache.batch_update_sent_files("test_session", files_info)

        # Verify all were saved
        for file_path, size, mtime in files_info:
            result = await cache.get_sent_file_info("test_session", file_path)
            assert result["size"] == size
            assert result["mtime"] == mtime

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_file_changed_since_last_send_new_file():
    """Test file_changed_since_last_send for a new file."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        # New file should return True
        result = await cache.file_changed_since_last_send(
            "test_session", "/api/new_file.py"
        )
        assert result is True

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_file_changed_since_last_send_mtime_changed():
    """Test file_changed_since_last_send when mtime changes."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        # Save initial file info
        await cache.update_sent_file_info(
            "test_session", "/api/file1.py", 12345, 1700000000
        )

        # Mock os.stat to return different mtime
        mock_stat = MagicMock()
        mock_stat.st_size = 12345  # Same size
        mock_stat.st_mtime = 1700001000  # Different mtime

        with patch("os.stat", return_value=mock_stat):
            result = await cache.file_changed_since_last_send(
                "test_session", "/api/file1.py"
            )
            assert result is True

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_file_changed_since_last_send_size_changed():
    """Test file_changed_since_last_send when size changes."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        # Save initial file info
        await cache.update_sent_file_info(
            "test_session", "/api/file1.py", 12345, 1700000000
        )

        # Mock os.stat to return different size
        mock_stat = MagicMock()
        mock_stat.st_size = 54321  # Different size
        mock_stat.st_mtime = 1700000000  # Same mtime

        with patch("os.stat", return_value=mock_stat):
            result = await cache.file_changed_since_last_send(
                "test_session", "/api/file1.py"
            )
            assert result is True

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_file_changed_since_last_send_no_change():
    """Test file_changed_since_last_send when nothing changes."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        # Save initial file info
        await cache.update_sent_file_info(
            "test_session", "/api/file1.py", 12345, 1700000000
        )

        # Mock os.stat to return same values
        mock_stat = MagicMock()
        mock_stat.st_size = 12345  # Same size
        mock_stat.st_mtime_ns = 1700000000  # Same mtime (in nanoseconds)

        with patch("os.stat", return_value=mock_stat):
            result = await cache.file_changed_since_last_send(
                "test_session", "/api/file1.py"
            )
            assert result is False

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_reset_session():
    """Test resetting all data for a session."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=3600)

        # Save stable list and file info
        await cache.save_stable_list("test_session", ["/api/file1.py", "/api/file2.py"])
        await cache.update_sent_file_info(
            "test_session", "/api/file1.py", 12345, 1700000000
        )

        # Reset the session
        await cache.reset_session("test_session")

        # Both should be gone
        assert await cache.get_stable_list("test_session") is None
        assert await cache.get_sent_file_info("test_session", "/api/file1.py") is None

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_ttl_expiration(monkeypatch):
    """Test that entries expire after TTL."""
    from tests.conftest import mock_clock

    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = StableListCache(db_path=db_path, ttl=1)  # 1 second TTL

        with mock_clock(monkeypatch) as tick:
            # Save stable list
            await cache.save_stable_list("test_session", ["/api/file1.py"])

            # Should be retrievable immediately
            assert await cache.get_stable_list("test_session") is not None

            # Advance virtual clock past TTL
            tick(2)

            # Should be expired
            assert await cache.get_stable_list("test_session") is None

        cache.close()
    finally:
        os.unlink(db_path)
