"""
Comprehensive tests for cache failure propagation, graceful degradation, and error handling.

This test suite validates the fix for Issue #6: Silent Cache Failures.
It ensures that cache errors are properly propagated (not swallowed),
the system degrades gracefully when cache is unavailable, and no failures are silent.
"""

import pytest
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock

from mcp_the_force.dedup.simple_cache import SimpleVectorStoreCache
from mcp_the_force.dedup.errors import (
    CacheTransactionError,
    CacheWriteError,
    CacheReadError,
)
from mcp_the_force.vectorstores.openai.openai_vectorstore import OpenAIVectorStore
from mcp_the_force.vectorstores.protocol import VSFile


# Fixture for a mock OpenAI client
@pytest.fixture
def mock_client():
    """Mock OpenAI client with typical responses."""
    client = AsyncMock()

    # Mock file upload response
    upload_response = MagicMock()
    upload_response.id = "file-mock-123"
    client.files.create = AsyncMock(return_value=upload_response)

    # Mock vector store operations
    client.vector_stores.file_batches.create_and_poll = AsyncMock()
    client.vector_stores.files.create = AsyncMock()
    client.files.delete = AsyncMock()

    return client


# Fixture for the OpenAIVectorStore with a mocked cache
@pytest.fixture
def store_with_mock_cache(mock_client):
    """OpenAIVectorStore with a mocked cache for controlled testing."""
    with patch(
        "mcp_the_force.vectorstores.openai.openai_vectorstore.get_cache"
    ) as mock_get_cache:
        mock_cache = MagicMock(spec=SimpleVectorStoreCache)
        mock_get_cache.return_value = mock_cache

        store = OpenAIVectorStore(
            client=mock_client, store_id="vs-test", name="test-store"
        )
        yield store, mock_cache


# A sample file for testing
@pytest.fixture
def test_file():
    """A sample VSFile for testing."""
    return VSFile(path="test.py", content="print('hello world')")


class TestCacheErrorHandling:
    """
    Tests for cache failure propagation, graceful degradation, and error handling.

    This validates the fix for Issue #6: Silent Cache Failures.
    """

    # 1. Cache Failure Propagation Tests
    # ==================================
    # Goal: Verify that cache exceptions are not swallowed and are handled correctly by upstream components.

    @pytest.mark.asyncio
    async def test_atomic_cache_or_get_propagates_as_graceful_upload(
        self, store_with_mock_cache, test_file, mock_client
    ):
        """
        Verify: When atomic_cache_or_get fails, OpenAIVectorStore treats it as a cache miss
                and proceeds with the upload, ensuring no data loss.
        """
        store, mock_cache = store_with_mock_cache

        # GIVEN: The atomic cache operation fails with a transaction error
        mock_cache.atomic_cache_or_get.side_effect = CacheTransactionError(
            "DB is locked"
        )

        # WHEN: add_files is called
        await store.add_files([test_file])

        # THEN: The file is still uploaded to OpenAI, demonstrating graceful degradation
        mock_client.files.create.assert_called_once()

        # AND: The cache's finalization method is called after successful upload
        mock_cache.finalize_file_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_finalize_cache_failure_propagates_and_is_handled(
        self, store_with_mock_cache, caplog
    ):
        """
        Verify: When finalize_file_id fails, the error is logged, but the overall
                operation doesn't fail, as the file is already uploaded and associated.
        """
        store, mock_cache = store_with_mock_cache

        # GIVEN: The cache finalization step fails
        mock_cache.finalize_file_id.side_effect = CacheWriteError("Cannot write to DB")

        # WHEN: The internal finalization method is called
        newly_uploaded = [("hash123", "file-123")]
        await store._finalize_cache_entries(newly_uploaded, mock_cache)

        # THEN: A warning is logged, but no exception is raised
        assert "Failed to finalize cache for file file-123" in caplog.text
        assert "CacheWriteError" in caplog.text or "Cannot write to DB" in caplog.text

    @pytest.mark.asyncio
    async def test_rollback_cleanup_failure_propagates_and_is_logged(
        self, store_with_mock_cache, caplog, mock_client
    ):
        """
        Verify: If cleaning up the cache during a rollback fails, the error is logged,
                and the file is still deleted from OpenAI.
        """
        store, mock_cache = store_with_mock_cache

        # GIVEN: The cache cleanup operation fails during a rollback
        mock_cache.cleanup_failed_upload.side_effect = CacheWriteError(
            "DB locked during cleanup"
        )

        # WHEN: A rollback is triggered
        failed_uploads = [("hash123", "file-to-delete")]
        await store._rollback_failed_uploads(failed_uploads, mock_cache)

        # THEN: An error is logged for the cache failure
        assert "Failed to clean up cache for hash hash123..." in caplog.text

        # AND: The attempt to delete the orphaned file from OpenAI still proceeds
        mock_client.files.delete.assert_called_once_with("file-to-delete")

    # 2. Graceful Degradation Tests
    # =============================
    # Goal: Confirm the system continues to function when the cache is unavailable.

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_read_error(
        self, store_with_mock_cache, test_file, mock_client
    ):
        """
        Verify: A CacheReadError is treated as a cache miss, triggering a normal upload.
        """
        store, mock_cache = store_with_mock_cache

        # GIVEN: The cache read operation fails
        mock_cache.atomic_cache_or_get.side_effect = CacheReadError(
            "Cannot read from DB"
        )

        # WHEN: add_files is called
        await store.add_files([test_file])

        # THEN: The file is uploaded as if it were a new file
        mock_client.files.create.assert_called_once()

        # AND: The cache finalization is still attempted after successful upload
        mock_cache.finalize_file_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_transaction_error(
        self, store_with_mock_cache, test_file, mock_client, caplog
    ):
        """
        Verify: A CacheTransactionError is handled gracefully with proper logging.
        """
        store, mock_cache = store_with_mock_cache

        # GIVEN: The cache transaction fails
        mock_cache.atomic_cache_or_get.side_effect = CacheTransactionError(
            "Atomic operation failed"
        )

        # WHEN: add_files is called
        await store.add_files([test_file])

        # THEN: The error is logged appropriately
        assert (
            "Cache operation failed for test.py, proceeding with upload" in caplog.text
        )

        # AND: The file is still uploaded
        mock_client.files.create.assert_called_once()

    # 3. Retry Logic Tests
    # ====================
    # Goal: Confirm that transient cache failures can be retried by an upstream component.

    @pytest.mark.asyncio
    async def test_operation_can_be_retried_after_transient_failure(
        self, store_with_mock_cache, test_file, mock_client
    ):
        """
        Verify: If a cache error occurs, a subsequent retry of the entire operation succeeds
                when the cache becomes available again.
        """
        store, mock_cache = store_with_mock_cache

        # GIVEN: The first attempt fails due to a transient cache error
        mock_cache.atomic_cache_or_get.side_effect = CacheTransactionError(
            "DB temporarily busy"
        )

        # WHEN: The first call to add_files is made
        await store.add_files([test_file])

        # THEN: The upload proceeds because of graceful degradation
        assert mock_client.files.create.call_count == 1

        # GIVEN: The cache is now working correctly
        mock_cache.atomic_cache_or_get.side_effect = None  # Remove the error
        mock_cache.atomic_cache_or_get.return_value = (
            None,
            True,
        )  # Cache miss, we are uploader

        # WHEN: A retry happens with a different file (simulating retry with same content)
        test_file2 = VSFile(path="test2.py", content="print('hello world')")
        await store.add_files([test_file2])

        # THEN: The second upload also succeeds
        assert mock_client.files.create.call_count == 2
        assert mock_cache.finalize_file_id.call_count == 2

    # 4. No Silent Failures Tests
    # ===========================
    # Goal: Ensure that any cache operation failure results in a log record.

    @pytest.mark.asyncio
    async def test_no_silent_failure_on_atomic_get(
        self, store_with_mock_cache, test_file, caplog
    ):
        """
        Verify: A failure in atomic_cache_or_get is logged and handled gracefully.
        """
        store, mock_cache = store_with_mock_cache
        mock_cache.atomic_cache_or_get.side_effect = CacheTransactionError(
            "DB is locked"
        )

        await store.add_files([test_file])

        assert (
            "Cache operation failed for test.py, proceeding with upload" in caplog.text
        )

    @pytest.mark.asyncio
    async def test_no_silent_failure_on_finalize(self, store_with_mock_cache, caplog):
        """
        Verify: A failure in finalize_file_id is logged and doesn't break the operation.
        """
        store, mock_cache = store_with_mock_cache
        mock_cache.finalize_file_id.side_effect = CacheWriteError("Cannot finalize")

        newly_uploaded = [("hash456", "file-456")]
        await store._finalize_cache_entries(newly_uploaded, mock_cache)

        assert "Failed to finalize cache for file file-456" in caplog.text

    @pytest.mark.asyncio
    async def test_no_silent_failure_on_cleanup(self, store_with_mock_cache, caplog):
        """
        Verify: A failure in cleanup_failed_upload is logged and doesn't break rollback.
        """
        store, mock_cache = store_with_mock_cache
        mock_cache.cleanup_failed_upload.side_effect = CacheWriteError("Cleanup failed")

        failed_uploads = [("hash789", "file-789")]
        await store._rollback_failed_uploads(failed_uploads, mock_cache)

        assert "Failed to clean up cache for hash hash789..." in caplog.text

    # 5. Error Context Tests
    # ======================
    # Goal: Verify that exceptions contain proper context, including the original error.

    def test_cache_write_error_contains_original_exception(self):
        """
        Verify: CacheWriteError properly chains the underlying sqlite3.Error.
        """
        with tempfile.NamedTemporaryFile() as tmp:
            cache = SimpleVectorStoreCache(tmp.name)

            # GIVEN: The database connection will raise a specific sqlite3.Error
            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute.side_effect = sqlite3.Error("disk I/O error")

                # WHEN: A cache write operation is performed
                with pytest.raises(CacheWriteError) as exc_info:
                    cache.cache_file("hash123", "file-123")

                # THEN: The raised exception contains the original cause
                assert isinstance(exc_info.value.__cause__, sqlite3.Error)
                assert "disk I/O error" in str(exc_info.value.__cause__)
                assert "Cache file operation failed after" in str(exc_info.value)

    def test_cache_transaction_error_contains_original_exception(self):
        """
        Verify: CacheTransactionError properly chains the underlying sqlite3.Error.
        """
        with tempfile.NamedTemporaryFile() as tmp:
            cache = SimpleVectorStoreCache(tmp.name)

            # GIVEN: The database connection will raise a specific sqlite3.Error during atomic operation
            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute.side_effect = sqlite3.Error(
                    "database is locked"
                )

                # WHEN: An atomic cache operation is performed
                with pytest.raises(CacheTransactionError) as exc_info:
                    cache.atomic_cache_or_get("hash123")

                # THEN: The raised exception contains the original cause
                assert isinstance(exc_info.value.__cause__, sqlite3.Error)
                assert "database is locked" in str(exc_info.value.__cause__)
                assert "Atomic cache or get operation failed after" in str(
                    exc_info.value
                )

    def test_cache_read_error_contains_original_exception(self):
        """
        Verify: CacheReadError properly chains the underlying sqlite3.Error.
        """
        with tempfile.NamedTemporaryFile() as tmp:
            cache = SimpleVectorStoreCache(tmp.name)

            # GIVEN: The database connection will raise a specific sqlite3.Error during read
            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute.side_effect = sqlite3.Error(
                    "database corrupted"
                )

                # WHEN: A cache read operation is performed
                with pytest.raises(CacheReadError) as exc_info:
                    cache.get_file_id("hash123")

                # THEN: The raised exception contains the original cause
                assert isinstance(exc_info.value.__cause__, sqlite3.Error)
                assert "database corrupted" in str(exc_info.value.__cause__)
                assert "Cache read operation failed" in str(exc_info.value)

    # 6. Integration Tests - Real Cache Behavior
    # ==========================================
    # Goal: Verify the actual cache methods raise the expected exceptions

    def test_real_cache_finalize_raises_on_sqlite_error(self):
        """
        Test that the actual cache implementation raises CacheWriteError when SQLite fails.
        """
        with tempfile.NamedTemporaryFile() as tmp:
            cache = SimpleVectorStoreCache(tmp.name)

            # GIVEN: A corrupted database connection
            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute.side_effect = sqlite3.Error("constraint failed")

                # WHEN: finalize_file_id is called
                # THEN: It should raise CacheWriteError (not return silently)
                with pytest.raises(CacheWriteError) as exc_info:
                    cache.finalize_file_id("hash123", "file-123")

                assert "Cache finalization operation failed" in str(exc_info.value)

    def test_real_cache_cleanup_raises_on_sqlite_error(self):
        """
        Test that the actual cache implementation raises CacheWriteError when cleanup fails.
        """
        with tempfile.NamedTemporaryFile() as tmp:
            cache = SimpleVectorStoreCache(tmp.name)

            # GIVEN: A failing database connection
            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute.side_effect = sqlite3.Error("disk full")

                # WHEN: cleanup_failed_upload is called
                # THEN: It should raise CacheWriteError (not return silently)
                with pytest.raises(CacheWriteError) as exc_info:
                    cache.cleanup_failed_upload("hash123")

                assert "Cache cleanup operation failed" in str(exc_info.value)

    def test_real_cache_atomic_raises_on_sqlite_error(self):
        """
        Test that the actual cache implementation raises CacheTransactionError when atomic operation fails.
        """
        with tempfile.NamedTemporaryFile() as tmp:
            cache = SimpleVectorStoreCache(tmp.name)

            # GIVEN: A failing database connection
            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute.side_effect = sqlite3.Error("database locked")

                # WHEN: atomic_cache_or_get is called
                # THEN: It should raise CacheTransactionError (not return (None, False))
                with pytest.raises(CacheTransactionError) as exc_info:
                    cache.atomic_cache_or_get("hash123")

                assert "Atomic cache or get operation failed" in str(exc_info.value)
