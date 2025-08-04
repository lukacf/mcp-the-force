"""
Comprehensive tests for SQLite retry logic in cache operations.

This test suite validates the fix for Issue #10: Missing SQLite Retry Logic.
It ensures that transient SQLite errors are properly retried with exponential backoff,
while non-retryable errors fail immediately.
"""

import pytest
import sqlite3
import tempfile
import time
from unittest.mock import patch, MagicMock

from mcp_the_force.dedup.simple_cache import DeduplicationCache
from mcp_the_force.dedup.errors import (
    CacheWriteError,
)
from mcp_the_force.dedup.retry import (
    is_retryable_sqlite_error,
    is_non_retryable_sqlite_error,
    calculate_delay,
    RetryConfig,
)


class TestRetryLogicFunctions:
    """Test the core retry logic functions."""

    def test_retryable_error_detection(self):
        """Test that retryable SQLite errors are correctly identified."""
        retryable_errors = [
            sqlite3.Error("database is locked"),
            sqlite3.Error("database is busy"),
            sqlite3.Error("cannot start a transaction within a transaction"),
            sqlite3.Error("disk i/o error"),
        ]

        for error in retryable_errors:
            assert is_retryable_sqlite_error(error), f"Should be retryable: {error}"
            assert not is_non_retryable_sqlite_error(
                error
            ), f"Should not be non-retryable: {error}"

    def test_non_retryable_error_detection(self):
        """Test that non-retryable SQLite errors are correctly identified."""
        non_retryable_errors = [
            sqlite3.Error("constraint failed"),
            sqlite3.Error("unique constraint failed"),
            sqlite3.Error("foreign key constraint failed"),
            sqlite3.Error("no such table"),
            sqlite3.Error("no such column"),
            sqlite3.Error("syntax error"),
            sqlite3.Error("database disk image is malformed"),
            sqlite3.Error("not a database"),
        ]

        for error in non_retryable_errors:
            assert is_non_retryable_sqlite_error(
                error
            ), f"Should be non-retryable: {error}"
            assert not is_retryable_sqlite_error(
                error
            ), f"Should not be retryable: {error}"

    def test_delay_calculation(self):
        """Test exponential backoff delay calculation."""
        config = RetryConfig(
            base_delay=0.1, backoff_multiplier=2.0, max_delay=1.0, jitter_factor=0.0
        )

        # Test exponential backoff without jitter
        delay_0 = calculate_delay(0, config)
        delay_1 = calculate_delay(1, config)
        delay_2 = calculate_delay(2, config)

        assert delay_0 == 0.1  # base_delay * (2^0) = 0.1
        assert delay_1 == 0.2  # base_delay * (2^1) = 0.2
        assert delay_2 == 0.4  # base_delay * (2^2) = 0.4

        # Test max delay cap
        delay_large = calculate_delay(10, config)
        assert delay_large == 1.0  # Should be capped at max_delay

    def test_jitter_adds_randomness(self):
        """Test that jitter adds randomness to delays."""
        config = RetryConfig(base_delay=0.1, jitter_factor=0.5)

        delays = [calculate_delay(0, config) for _ in range(10)]

        # All delays should be different due to jitter
        assert len(set(delays)) > 1, "Jitter should create different delays"

        # All delays should be >= base_delay
        assert all(d >= 0.1 for d in delays), "Delays should be at least base_delay"


class TestCacheFileRetry:
    """Test retry logic for cache_file method."""

    async def test_cache_file_retries_on_database_busy(self):
        """Test that cache_file retries on database busy errors."""
        with tempfile.NamedTemporaryFile() as tmp:
            cache = DeduplicationCache(tmp.name)

            # Mock connection to simulate database busy error, then success
            call_count = 0

            def mock_execute(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:  # Fail first 2 attempts
                    raise sqlite3.Error("database is busy")
                # Success on 3rd attempt
                return MagicMock()

            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute = mock_execute

                # Should succeed after retries
                await cache.cache_file("hash123", "file-123")

                # Should have been called 3 times (2 failures + 1 success)
                assert call_count == 3

    async def test_cache_file_fails_on_non_retryable_error(self):
        """Test that cache_file fails immediately on non-retryable errors."""
        with tempfile.NamedTemporaryFile() as tmp:
            cache = DeduplicationCache(tmp.name)

            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute.side_effect = sqlite3.Error("constraint failed")

                # Should fail immediately without retries
                with pytest.raises(CacheWriteError) as exc_info:
                    await cache.cache_file("hash123", "file-123")

                assert "Cache file operation failed: constraint failed" in str(
                    exc_info.value
                )
                # Should only be called once (no retries for non-retryable errors)
                assert mock_connection.execute.call_count == 1


class TestCacheStoreRetry:
    """Test retry logic for cache_store method."""

    async def test_cache_store_retries_on_database_locked(self):
        """Test that cache_store retries on database locked errors."""
        with tempfile.NamedTemporaryFile() as tmp:
            cache = DeduplicationCache(tmp.name)

            call_count = 0

            def mock_execute(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:  # Fail first attempt
                    raise sqlite3.Error("database is locked")
                # Success on 2nd attempt
                return MagicMock()

            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute = mock_execute

                # Should succeed after retry
                await cache.cache_store("fileset123", "store-456", "openai")

                # Should have been called 2 times (1 failure + 1 success)
                assert call_count == 2


class TestCleanupOldEntriesRetry:
    """Test retry logic for cleanup_old_entries method."""

    async def test_cleanup_old_entries_retries_on_disk_io_error(self):
        """Test that cleanup_old_entries retries on disk I/O errors."""
        with tempfile.NamedTemporaryFile() as tmp:
            cache = DeduplicationCache(tmp.name)

            call_count = 0

            def mock_execute(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:  # Fail first 2 attempts
                    raise sqlite3.Error("disk i/o error")
                # Success on 3rd attempt - return mock cursor with rowcount
                mock_cursor = MagicMock()
                mock_cursor.rowcount = 5
                return mock_cursor

            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute = mock_execute

                # Should succeed after retries
                await cache.cleanup_old_entries(max_age_days=30)

                # Should have been called 4 times (2 failed attempts + 1 successful attempt with 2 queries)
                assert call_count == 4  # 2 failed attempts + 2 successful queries


class TestGetStoreIdRetry:
    """Test retry logic for get_store_id method."""

    async def test_get_store_id_retries_on_database_busy(self):
        """Test that get_store_id retries on database busy errors."""
        with tempfile.NamedTemporaryFile() as tmp:
            cache = DeduplicationCache(tmp.name)

            call_count = 0

            def mock_execute(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:  # Fail first attempt
                    raise sqlite3.Error("database is busy")
                # Success on 2nd attempt
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = ("store-123", "openai")
                return mock_cursor

            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute = mock_execute

                # Should succeed after retry
                result = await cache.get_store_id("fileset123")

                assert result == {"store_id": "store-123", "provider": "openai"}
                assert call_count == 2


class TestGetStatsRetry:
    """Test retry logic for get_stats method."""

    async def test_get_stats_retries_on_database_locked(self):
        """Test that get_stats retries on database locked errors."""
        with tempfile.NamedTemporaryFile() as tmp:
            cache = DeduplicationCache(tmp.name)

            attempt_count = 0
            execute_count = 0

            def mock_execute(*args, **kwargs):
                nonlocal attempt_count, execute_count
                execute_count += 1
                # get_stats has 3 queries, so we simulate failure on first attempt only
                if attempt_count == 0:
                    attempt_count += 1
                    raise sqlite3.Error("database is locked")
                # Success on second attempt
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = [10]  # Mock count
                return mock_cursor

            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute = mock_execute

                # Should succeed after retries
                stats = await cache.get_stats()

                assert stats["file_count"] == 10
                assert stats["store_count"] == 10
                assert stats["pending_uploads"] == 10
                assert stats["cache_type"] == "DeduplicationCache"

                # Should have been called 4 times total (1 failed + 3 successful)
                assert execute_count == 4


class TestRetryIntegration:
    """Integration tests for retry behavior across multiple operations."""

    async def test_mixed_retryable_and_non_retryable_errors(self):
        """Test handling of mixed error types in sequence."""
        with tempfile.NamedTemporaryFile() as tmp:
            cache = DeduplicationCache(tmp.name)

            # First operation: retryable error that succeeds on retry
            call_count = 0

            def mock_execute_retryable(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise sqlite3.Error("database is busy")
                return MagicMock()

            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute = mock_execute_retryable

                # Should succeed after retry
                await cache.cache_file("hash1", "file-1")
                assert call_count == 2

            # Second operation: non-retryable error that fails immediately
            with patch.object(cache, "_get_connection") as mock_conn2:
                mock_connection2 = MagicMock()
                mock_conn2.return_value = mock_connection2
                mock_connection2.__enter__.return_value = mock_connection2
                mock_connection2.execute.side_effect = sqlite3.Error(
                    "constraint failed"
                )

                # Should fail immediately
                with pytest.raises(CacheWriteError):
                    await cache.cache_file("hash2", "file-2")

                # Should only be called once (no retries)
                assert mock_connection2.execute.call_count == 1

    async def test_retry_timing_behavior(self):
        """Test that retry delays are actually applied."""
        with tempfile.NamedTemporaryFile() as tmp:
            cache = DeduplicationCache(tmp.name)

            call_times = []

            def mock_execute(*args, **kwargs):
                call_times.append(time.time())
                if len(call_times) <= 2:  # Fail first 2 attempts
                    raise sqlite3.Error("database is busy")
                return MagicMock()

            with patch.object(cache, "_get_connection") as mock_conn:
                mock_connection = MagicMock()
                mock_conn.return_value = mock_connection
                mock_connection.__enter__.return_value = mock_connection
                mock_connection.execute = mock_execute

                await cache.cache_file("hash123", "file-123")

                # Should have 3 calls total
                assert len(call_times) == 3

                # Verify delays between retries (allowing for some timing variance)
                delay1 = call_times[1] - call_times[0]
                delay2 = call_times[2] - call_times[1]

                # First retry should be around 0.1s, second around 0.2s (with jitter)
                assert (
                    0.05 < delay1 < 0.5
                ), f"First retry delay {delay1} outside expected range"
                assert (
                    0.1 < delay2 < 0.8
                ), f"Second retry delay {delay2} outside expected range"

                # Second delay should be larger than first (exponential backoff)
                assert delay2 > delay1, "Exponential backoff should increase delays"
