"""Comprehensive concurrency tests for DeduplicationCache atomic operations.

These tests validate that the atomic cache operations prevent race conditions
under high concurrency scenarios, ensuring no duplicate uploads occur.

Tests focus on:
- Multiple concurrent processes trying to upload the same file
- Atomic workflow: atomic_cache_or_get -> upload -> finalize_file_id -> cleanup_failed_upload
- Edge cases: concurrent failures, database locks, high concurrency
- Verification that only one process performs actual upload
"""

import pytest
import threading
import time
import sqlite3
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from mcp_the_force.dedup.simple_cache import DeduplicationCache


@pytest.fixture
def temp_cache_db():
    """Create a temporary cache database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    # Create cache instance
    cache = DeduplicationCache(db_path)

    yield cache

    # Cleanup
    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture
def content_hashes():
    """Generate test content hashes."""
    return [
        "a" * 64,  # SHA-256 length hash
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
    ]


class TestAtomicCacheOperations:
    """Test atomic cache operations under various concurrency scenarios."""

    async def test_atomic_cache_or_get_basic_functionality(
        self, temp_cache_db, content_hashes
    ):
        """Test basic atomic_cache_or_get functionality without concurrency."""
        cache = temp_cache_db
        content_hash = content_hashes[0]

        # First call should win and return (None, True)
        file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
        assert file_id is None
        assert we_are_uploader is True

        # Verify PENDING entry was created
        cached_file_id = await cache.get_file_id(content_hash)
        assert cached_file_id == "PENDING"

        # Second call should lose and return ("PENDING", False)
        file_id2, we_are_uploader2 = await cache.atomic_cache_or_get(content_hash)
        assert file_id2 == "PENDING"
        assert we_are_uploader2 is False

        # Finalize the upload
        real_file_id = "file-123456"
        await cache.finalize_file_id(content_hash, real_file_id)

        # Third call should return the real file_id
        file_id3, we_are_uploader3 = await cache.atomic_cache_or_get(content_hash)
        assert file_id3 == real_file_id
        assert we_are_uploader3 is False

    async def test_finalize_file_id_idempotency(self, temp_cache_db, content_hashes):
        """Test that finalize_file_id is idempotent and safe for concurrent calls."""
        cache = temp_cache_db
        content_hash = content_hashes[0]

        # Reserve the hash
        file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
        assert we_are_uploader is True

        # Finalize multiple times with same ID
        real_file_id = "file-123456"
        await cache.finalize_file_id(content_hash, real_file_id)
        await cache.finalize_file_id(content_hash, real_file_id)  # Should be safe
        await cache.finalize_file_id(content_hash, real_file_id)  # Should be safe

        # Verify final state
        cached_file_id = await cache.get_file_id(content_hash)
        assert cached_file_id == real_file_id

        # Try to finalize with different ID (should be ignored)
        await cache.finalize_file_id(content_hash, "file-different")
        cached_file_id = await cache.get_file_id(content_hash)
        assert cached_file_id == real_file_id  # Should remain unchanged

    async def test_cleanup_failed_upload_safety(self, temp_cache_db, content_hashes):
        """Test that cleanup_failed_upload is safe and only removes PENDING entries."""
        cache = temp_cache_db
        content_hash = content_hashes[0]

        # Reserve the hash
        file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
        assert we_are_uploader is True

        # Cleanup should remove PENDING entry
        await cache.cleanup_failed_upload(content_hash)
        cached_file_id = await cache.get_file_id(content_hash)
        assert cached_file_id is None

        # Next attempt should succeed again
        file_id2, we_are_uploader2 = await cache.atomic_cache_or_get(content_hash)
        assert we_are_uploader2 is True

        # Finalize the upload
        real_file_id = "file-123456"
        await cache.finalize_file_id(content_hash, real_file_id)

        # Cleanup should NOT remove finalized entries
        await cache.cleanup_failed_upload(content_hash)
        cached_file_id = await cache.get_file_id(content_hash)
        assert cached_file_id == real_file_id  # Should remain


class TestConcurrentUploadPrevention:
    """Test that concurrent uploads are prevented through atomic operations."""

    async def test_concurrent_atomic_cache_or_get_thread_safety(
        self, temp_cache_db, content_hashes
    ):
        """Test that only one thread wins the atomic_cache_or_get race."""
        cache = temp_cache_db
        content_hash = content_hashes[0]

        results = []
        exception_count = 0

        async def attempt_upload(thread_id):
            """Simulate a thread attempting to upload."""
            try:
                file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
                results.append((thread_id, file_id, we_are_uploader))
                return (thread_id, file_id, we_are_uploader)
            except Exception as e:
                nonlocal exception_count
                exception_count += 1
                results.append((thread_id, f"ERROR: {e}", False))
                return (thread_id, f"ERROR: {e}", False)

        # Run 20 concurrent tasks
        num_threads = 20
        tasks = [attempt_upload(i) for i in range(num_threads)]
        await asyncio.gather(*tasks)

        # Analyze results
        winners = [r for r in results if r[2] is True]  # we_are_uploader = True
        losers = [
            r for r in results if r[2] is False and not str(r[1]).startswith("ERROR")
        ]

        # Assertions
        assert (
            len(winners) == 1
        ), f"Expected exactly 1 winner, got {len(winners)}: {winners}"
        assert (
            len(losers) >= num_threads - 1
        ), f"Expected at least {num_threads - 1} losers, got {len(losers)}"
        assert (
            exception_count == 0
        ), f"Unexpected exceptions occurred: {exception_count}"

        # Verify all losers see PENDING
        for loser in losers:
            assert loser[1] == "PENDING", f"Loser should see PENDING, got: {loser[1]}"

    async def test_concurrent_workflow_completion(self, temp_cache_db, content_hashes):
        """Test complete concurrent workflow: reserve -> upload -> finalize."""
        cache = temp_cache_db
        content_hash = content_hashes[0]

        upload_attempts = []
        finalization_attempts = []

        async def complete_upload_workflow(thread_id):
            """Simulate complete upload workflow."""
            try:
                # Step 1: Attempt to reserve
                file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)

                if we_are_uploader:
                    upload_attempts.append(thread_id)

                    # Simulate upload work (with some delay to increase race window)
                    time.sleep(0.01)

                    # Step 2: Finalize with real file_id
                    real_file_id = f"file-{thread_id}-{int(time.time())}"
                    await cache.finalize_file_id(content_hash, real_file_id)
                    finalization_attempts.append((thread_id, real_file_id))

                    return ("winner", thread_id, real_file_id)
                else:
                    # Check what we got
                    return ("loser", thread_id, file_id)

            except Exception as e:
                return ("error", thread_id, str(e))

        # Run concurrent workflows
        num_threads = 15
        tasks = [complete_upload_workflow(i) for i in range(num_threads)]
        results = await asyncio.gather(*tasks)

        # Analyze results
        winners = [r for r in results if r[0] == "winner"]
        [r for r in results if r[0] == "loser"]
        errors = [r for r in results if r[0] == "error"]

        # Assertions
        assert len(winners) == 1, f"Expected exactly 1 winner, got {len(winners)}"
        assert (
            len(upload_attempts) == 1
        ), f"Expected exactly 1 upload attempt, got {len(upload_attempts)}"
        assert (
            len(finalization_attempts) == 1
        ), f"Expected exactly 1 finalization, got {len(finalization_attempts)}"
        assert len(errors) == 0, f"Unexpected errors: {errors}"

        # Verify final state
        final_file_id = await cache.get_file_id(content_hash)
        assert final_file_id is not None
        assert final_file_id != "PENDING"
        assert final_file_id.startswith("file-")

    async def test_concurrent_failure_recovery(self, temp_cache_db, content_hashes):
        """Test that failed uploads are properly cleaned up and retryable."""
        cache = temp_cache_db
        content_hash = content_hashes[0]

        first_attempt_results = []
        retry_attempt_results = []

        async def failing_upload_workflow(thread_id, should_fail=True):
            """Simulate upload workflow that fails."""
            try:
                file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)

                if we_are_uploader:
                    if should_fail:
                        # Simulate upload failure
                        await cache.cleanup_failed_upload(content_hash)
                        first_attempt_results.append(("failed", thread_id))
                        return ("failed", thread_id)
                    else:
                        # Successful upload
                        real_file_id = f"file-retry-{thread_id}"
                        await cache.finalize_file_id(content_hash, real_file_id)
                        retry_attempt_results.append(
                            ("success", thread_id, real_file_id)
                        )
                        return ("success", thread_id, real_file_id)
                else:
                    return ("blocked", thread_id, file_id)

            except Exception as e:
                return ("error", thread_id, str(e))

        # First round: All attempts fail
        num_threads = 10
        tasks = [
            failing_upload_workflow(i, should_fail=True) for i in range(num_threads)
        ]
        first_results = await asyncio.gather(*tasks)

        # Verify at least one failure occurred (others were blocked)
        # Note: Due to race conditions, multiple threads might succeed in atomic_cache_or_get
        # if they attempt it after cleanup, but only one cleanup per thread is expected
        failed_attempts = [r for r in first_results if r[0] == "failed"]
        [r for r in first_results if r[0] == "blocked"]

        assert (
            len(failed_attempts) >= 1
        ), f"Expected at least 1 failed attempt, got {len(failed_attempts)}"
        assert (
            len(failed_attempts) <= num_threads
        ), f"Expected at most {num_threads} failed attempts, got {len(failed_attempts)}"

        # Verify hash is available for retry (last cleanup should have cleared it)
        cached_file_id = await cache.get_file_id(content_hash)
        assert cached_file_id is None

        # Second round: One should succeed
        tasks = [
            failing_upload_workflow(i + 100, should_fail=False)
            for i in range(num_threads)
        ]
        retry_results = await asyncio.gather(*tasks)

        # Verify exactly one retry succeeded
        successful_retries = [r for r in retry_results if r[0] == "success"]
        blocked_retries = [r for r in retry_results if r[0] == "blocked"]

        assert (
            len(successful_retries) == 1
        ), f"Expected exactly 1 successful retry, got {len(successful_retries)}"
        assert len(blocked_retries) >= num_threads - 1

        # Verify final state
        final_file_id = await cache.get_file_id(content_hash)
        assert final_file_id is not None
        assert final_file_id.startswith("file-retry-")


class TestHighConcurrencyScenarios:
    """Test behavior under extreme concurrency scenarios."""

    async def test_high_concurrency_multiple_hashes(
        self, temp_cache_db, content_hashes
    ):
        """Test concurrent operations on multiple different hashes."""
        cache = temp_cache_db

        results_by_hash = {hash_val: [] for hash_val in content_hashes}

        async def process_hash_concurrently(thread_id, content_hash):
            """Process a specific hash."""
            try:
                file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)

                if we_are_uploader:
                    # Simulate some work
                    time.sleep(0.001)
                    real_file_id = f"file-{content_hash[:8]}-{thread_id}"
                    await cache.finalize_file_id(content_hash, real_file_id)
                    return ("winner", thread_id, content_hash, real_file_id)
                else:
                    return ("loser", thread_id, content_hash, file_id)

            except Exception as e:
                return ("error", thread_id, content_hash, str(e))

        # Create tasks for multiple threads per hash
        tasks = []
        threads_per_hash = 8

        for content_hash in content_hashes:
            for thread_id in range(threads_per_hash):
                tasks.append((thread_id, content_hash))

        # Execute all tasks concurrently
        async_tasks = [
            process_hash_concurrently(thread_id, content_hash)
            for thread_id, content_hash in tasks
        ]
        results = await asyncio.gather(*async_tasks)

        # Group results by hash
        for result in results:
            if len(result) >= 3:
                content_hash = result[2]
                results_by_hash[content_hash].append(result)

        # Verify each hash has exactly one winner
        for content_hash, hash_results in results_by_hash.items():
            winners = [r for r in hash_results if r[0] == "winner"]
            losers = [r for r in hash_results if r[0] == "loser"]
            errors = [r for r in hash_results if r[0] == "error"]

            assert (
                len(winners) == 1
            ), f"Hash {content_hash[:8]} should have exactly 1 winner, got {len(winners)}"
            assert (
                len(losers) >= threads_per_hash - 1
            ), f"Hash {content_hash[:8]} should have at least {threads_per_hash - 1} losers"
            assert (
                len(errors) == 0
            ), f"Hash {content_hash[:8]} had unexpected errors: {errors}"

            # Verify final state for this hash
            final_file_id = await cache.get_file_id(content_hash)
            assert final_file_id is not None
            assert final_file_id != "PENDING"

    async def test_database_lock_timeout_behavior(self, temp_cache_db, content_hashes):
        """Test behavior when database lock timeout is approached."""
        cache = temp_cache_db
        content_hash = content_hashes[0]

        # Simulate a long-running transaction that holds a lock
        def long_running_transaction():
            """Hold a write lock for extended period."""
            # Create a separate connection to avoid interfering with cache._conn
            import sqlite3

            separate_conn = sqlite3.connect(cache.db_path)
            separate_conn.execute("PRAGMA busy_timeout = 30000")
            try:
                separate_conn.execute("BEGIN IMMEDIATE")
                # Insert something to acquire write lock
                separate_conn.execute(
                    "INSERT OR IGNORE INTO file_cache (content_hash, file_id, created_at) VALUES (?, ?, ?)",
                    ("lock_holder", "PENDING", int(time.time())),
                )
                # Hold lock for a while
                time.sleep(2)
                separate_conn.commit()
            except Exception:
                separate_conn.rollback()
                raise
            finally:
                separate_conn.close()

        # Start the long-running transaction in background
        lock_holder_thread = threading.Thread(target=long_running_transaction)
        lock_holder_thread.start()

        # Give it time to acquire the lock
        time.sleep(0.1)

        # Now try concurrent operations while lock is held
        results = []

        async def attempt_during_lock(thread_id):
            """Attempt operation while lock is held."""
            try:
                start_time = time.time()
                file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
                end_time = time.time()
                return ("success", thread_id, end_time - start_time, we_are_uploader)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) or "busy" in str(e):
                    return ("timeout", thread_id, str(e))
                else:
                    return ("error", thread_id, str(e))
            except Exception as e:
                return ("error", thread_id, str(e))

        # Launch concurrent attempts
        async_tasks = [attempt_during_lock(i) for i in range(5)]

        # Wait for lock holder to finish
        lock_holder_thread.join()

        # Collect results
        results = await asyncio.gather(*async_tasks)

        # Analyze results - some should succeed (after lock is released)
        successes = [r for r in results if r[0] == "success"]
        [r for r in results if r[0] == "timeout"]
        [r for r in results if r[0] == "error"]

        # At least some operations should have succeeded eventually
        assert len(successes) > 0, f"Expected some successes, got results: {results}"

        # Exactly one should be the uploader
        uploaders = [r for r in successes if r[3] is True]
        assert len(uploaders) == 1, f"Expected exactly 1 uploader, got {len(uploaders)}"

    async def test_stress_test_atomic_operations(self, temp_cache_db):
        """Stress test with many concurrent operations on same hash."""
        cache = temp_cache_db
        content_hash = "stress_test_hash_" + "x" * 48  # 64 char total

        operation_results = []

        async def stress_operation(operation_id):
            """Perform stress operation."""
            try:
                # Random delay to increase race conditions
                time.sleep(0.001 * (operation_id % 5))

                file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)

                if we_are_uploader:
                    # Winner - complete the upload
                    time.sleep(0.01)  # Simulate upload time
                    real_file_id = f"stress-file-{operation_id}"
                    await cache.finalize_file_id(content_hash, real_file_id)
                    return ("uploaded", operation_id, real_file_id)
                else:
                    # Loser - check what we got
                    return ("blocked", operation_id, file_id)

            except Exception as e:
                return ("error", operation_id, str(e))

        # Launch stress test with many concurrent operations
        num_operations = 50
        async_tasks = [stress_operation(i) for i in range(num_operations)]
        operation_results = await asyncio.gather(*async_tasks)

        # Analyze stress test results
        uploaded = [r for r in operation_results if r[0] == "uploaded"]
        blocked = [r for r in operation_results if r[0] == "blocked"]
        errors = [r for r in operation_results if r[0] == "error"]

        # Critical assertions for stress test
        assert (
            len(uploaded) == 1
        ), f"Stress test failed: expected exactly 1 upload, got {len(uploaded)}"
        assert (
            len(blocked) >= num_operations - 1
        ), f"Expected at least {num_operations - 1} blocked operations"
        assert len(errors) == 0, f"Stress test had unexpected errors: {errors}"

        # Verify final consistent state
        final_file_id = await cache.get_file_id(content_hash)
        assert final_file_id is not None
        assert final_file_id != "PENDING"
        assert final_file_id.startswith("stress-file-")

        # Verify cache stats are consistent
        stats = await cache.get_stats()
        assert (
            stats["pending_uploads"] == 0
        ), "Should have no pending uploads after stress test"


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling in atomic operations."""

    async def test_concurrent_cleanup_and_finalize(self, temp_cache_db, content_hashes):
        """Test race between cleanup_failed_upload and finalize_file_id."""
        cache = temp_cache_db
        content_hash = content_hashes[0]

        # Reserve the hash
        file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
        assert we_are_uploader is True

        results = []

        async def attempt_finalize():
            """Attempt to finalize."""
            try:
                await cache.finalize_file_id(content_hash, "file-finalized")
                results.append("finalized")
            except Exception as e:
                results.append(f"finalize_error: {e}")

        async def attempt_cleanup():
            """Attempt to cleanup."""
            try:
                # Small delay to increase race window
                time.sleep(0.01)
                await cache.cleanup_failed_upload(content_hash)
                results.append("cleaned_up")
            except Exception as e:
                results.append(f"cleanup_error: {e}")

        # Run both operations concurrently
        await asyncio.gather(attempt_finalize(), attempt_cleanup())

        # Check final state - finalize should win if it runs first
        final_file_id = await cache.get_file_id(content_hash)

        if "finalized" in results:
            # Finalize won the race
            assert final_file_id == "file-finalized"
        else:
            # Cleanup won the race
            assert final_file_id is None

        # Both operations should have completed without errors
        error_results = [r for r in results if "error" in r]
        assert len(error_results) == 0, f"Unexpected errors: {error_results}"

    async def test_database_corruption_resilience(self, temp_cache_db, content_hashes):
        """Test that database access issues raise proper exceptions instead of silent failures."""
        from mcp_the_force.dedup.errors import (
            CacheTransactionError,
            CacheWriteError,
            CacheReadError,
        )

        cache = temp_cache_db
        content_hash = content_hashes[0]

        # Test with temporarily inaccessible database
        original_conn = cache._conn

        # Mock connection that raises errors
        failing_conn = MagicMock()
        failing_conn.__enter__ = MagicMock(
            side_effect=sqlite3.OperationalError("Database is locked")
        )
        failing_conn.__exit__ = MagicMock(return_value=None)

        # Temporarily break database access
        cache._conn = failing_conn

        try:
            # These should now raise proper exceptions instead of returning safe defaults
            with pytest.raises(CacheTransactionError) as exc_info:
                await cache.atomic_cache_or_get(content_hash)
            assert "Database is locked" in str(exc_info.value.__cause__)

            # Read operations should raise CacheReadError
            with pytest.raises(CacheReadError) as exc_info:
                await cache.get_file_id(content_hash)
            assert "Database is locked" in str(exc_info.value.__cause__)

            # Write operations should raise CacheWriteError
            with pytest.raises(CacheWriteError) as exc_info:
                await cache.finalize_file_id(content_hash, "test-file")
            assert "Database is locked" in str(exc_info.value.__cause__)

            with pytest.raises(CacheWriteError) as exc_info:
                await cache.cleanup_failed_upload(content_hash)
            assert "Database is locked" in str(exc_info.value.__cause__)

        finally:
            # Restore normal operation
            cache._conn = original_conn

        # Verify normal operation restored
        file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
        assert file_id is None
        assert we_are_uploader is True

    async def test_pending_entry_stale_detection(self, temp_cache_db, content_hashes):
        """Test detection and handling of stale PENDING entries."""
        cache = temp_cache_db
        content_hash = content_hashes[0]

        # Create a stale PENDING entry by directly inserting old timestamp
        old_timestamp = int(time.time()) - 3600  # 1 hour ago

        with cache._lock:
            if cache._conn is not None:
                cache._conn.execute(
                    "INSERT INTO file_cache (content_hash, file_id, created_at) VALUES (?, ?, ?)",
                    (content_hash, "PENDING", old_timestamp),
                )
                cache._conn.commit()

        # Verify the stale entry exists
        cached_file_id = await cache.get_file_id(content_hash)
        assert cached_file_id == "PENDING"

        # Attempt atomic_cache_or_get - should detect existing entry
        file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
        assert file_id == "PENDING"
        assert we_are_uploader is False

        # Manual cleanup of stale entry
        await cache.cleanup_failed_upload(content_hash)

        # Now should be able to proceed
        file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
        assert file_id is None
        assert we_are_uploader is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
