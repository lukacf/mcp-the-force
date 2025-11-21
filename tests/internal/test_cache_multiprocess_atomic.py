"""Multi-process concurrency tests for DeduplicationCache atomic operations.

These tests validate that atomic cache operations prevent race conditions
even across separate Python processes, which is the most realistic scenario
for real-world usage where multiple CLI invocations might run simultaneously.

Tests focus on:
- Multiple processes trying to upload the same file simultaneously
- Process-level atomic operations and SQLite WAL mode effectiveness
- Real-world scenarios where multiple users/sessions upload identical files
- Recovery from process crashes during upload
"""

import pytest
import multiprocessing
import time
import tempfile
import os
from pathlib import Path

from mcp_the_force.dedup.simple_cache import DeduplicationCache


# Global test database path for sharing between processes
TEST_DB_PATH = None


def setup_test_database():
    """Set up a temporary test database."""
    global TEST_DB_PATH
    if TEST_DB_PATH is None:
        tmp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        TEST_DB_PATH = tmp_file.name
        tmp_file.close()

    # Initialize the cache to create tables
    DeduplicationCache(TEST_DB_PATH)
    return TEST_DB_PATH


def cleanup_test_database():
    """Clean up the test database."""
    global TEST_DB_PATH
    if TEST_DB_PATH and Path(TEST_DB_PATH).exists():
        try:
            Path(TEST_DB_PATH).unlink()
        except Exception:
            pass
    TEST_DB_PATH = None


def worker_atomic_cache_attempt(args):
    """Worker function for process-based atomic cache attempts."""
    process_id, content_hash, db_path = args

    try:
        # Create cache instance in this process
        cache = DeduplicationCache(db_path)

        # Use synchronous version for multiprocessing compatibility
        file_id, we_are_uploader = _sync_atomic_cache_or_get(cache, content_hash)

        return {
            "process_id": process_id,
            "file_id": file_id,
            "we_are_uploader": we_are_uploader,
            "status": "success",
        }

    except Exception as e:
        return {
            "process_id": process_id,
            "file_id": None,
            "we_are_uploader": False,
            "status": "error",
            "error": str(e),
        }


def _sync_atomic_cache_or_get(cache, content_hash, placeholder="PENDING"):
    """Synchronous version of atomic_cache_or_get for multiprocessing tests."""
    if cache._conn is None:
        raise RuntimeError("Database connection is closed")

    now = int(time.time())
    from contextlib import nullcontext

    # Cross-process guard mirrors the production cache
    cm = cache._process_lock() if hasattr(cache, "_process_lock") else nullcontext()

    with cm, cache._lock, cache._conn:
        # Use EXCLUSIVE to ensure only one process can perform the insert at a time.
        cache._conn.execute("BEGIN EXCLUSIVE")

        try:
            # Attempt to atomically reserve this content hash (RETURNING avoids rowcount ambiguity)
            cursor = cache._conn.execute(
                """
                INSERT INTO file_cache (content_hash, file_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(content_hash) DO NOTHING
                RETURNING content_hash
                """,
                (content_hash, placeholder, now, now),
            )

            row = cursor.fetchone()
            we_are_uploader = row is not None

            if not we_are_uploader:
                # Another process already has this hash - fetch the current value
                cursor = cache._conn.execute(
                    "SELECT file_id FROM file_cache WHERE content_hash = ?",
                    (content_hash,),
                )
                result = cursor.fetchone()
                existing_file_id = result[0] if result else None
                cache._conn.commit()
                return existing_file_id, False
            else:
                # We successfully reserved this hash
                cache._conn.commit()
                return None, True

        except Exception:
            cache._conn.rollback()
            raise


def _sync_finalize_file_id(cache, content_hash, file_id):
    """Synchronous version of finalize_file_id for multiprocessing tests."""
    if cache._conn is None:
        raise RuntimeError("Database connection is closed")

    now = int(time.time())
    with cache._lock, cache._conn:
        cache._conn.execute(
            """
            UPDATE file_cache 
            SET file_id = ?, updated_at = ?
            WHERE content_hash = ? AND file_id = 'PENDING'
            """,
            (file_id, now, content_hash),
        )
        cache._conn.commit()


def _sync_cleanup_failed_upload(cache, content_hash):
    """Synchronous version of cleanup_failed_upload for multiprocessing tests."""
    if cache._conn is None:
        raise RuntimeError("Database connection is closed")

    with cache._lock, cache._conn:
        cache._conn.execute(
            "DELETE FROM file_cache WHERE content_hash = ? AND file_id = 'PENDING'",
            (content_hash,),
        )
        cache._conn.commit()


def _sync_get_file_id(cache, content_hash):
    """Synchronous version of get_file_id for multiprocessing tests."""
    if cache._conn is None:
        raise RuntimeError("Database connection is closed")

    with cache._lock, cache._conn:
        cursor = cache._conn.execute(
            "SELECT file_id FROM file_cache WHERE content_hash = ?",
            (content_hash,),
        )
        result = cursor.fetchone()
        return result[0] if result else None


def worker_complete_upload_workflow(args):
    """Worker function for complete upload workflow in separate process."""
    process_id, content_hash, db_path = args

    try:
        # Create cache instance in this process
        cache = DeduplicationCache(db_path)

        # Step 1: Attempt to reserve
        file_id, we_are_uploader = _sync_atomic_cache_or_get(cache, content_hash)

        if we_are_uploader:
            # Step 2: Simulate upload work
            time.sleep(0.05)  # Simulate upload time

            # Step 3: Finalize with real file_id
            real_file_id = f"file-process-{process_id}-{int(time.time())}"
            _sync_finalize_file_id(cache, content_hash, real_file_id)

            return {
                "process_id": process_id,
                "status": "uploaded",
                "file_id": real_file_id,
                "we_are_uploader": True,
            }
        else:
            # Not the uploader - just return what we got
            return {
                "process_id": process_id,
                "status": "blocked",
                "file_id": file_id,
                "we_are_uploader": False,
            }

    except Exception as e:
        return {
            "process_id": process_id,
            "status": "error",
            "error": str(e),
            "we_are_uploader": False,
        }


def worker_failing_upload_workflow(args):
    """Worker function that simulates failing upload workflow."""
    process_id, content_hash, db_path, should_fail = args

    try:
        cache = DeduplicationCache(db_path)

        # Attempt to reserve
        file_id, we_are_uploader = _sync_atomic_cache_or_get(cache, content_hash)

        if we_are_uploader:
            # Simulate upload work - increased sleep to reduce race condition flakiness
            # This gives other processes time to attempt reservation before cleanup
            time.sleep(0.2)  # Increased from 0.02 to 0.2 seconds

            if should_fail:
                # Simulate upload failure and cleanup
                _sync_cleanup_failed_upload(cache, content_hash)
                return {
                    "process_id": process_id,
                    "status": "failed_and_cleaned",
                    "we_are_uploader": True,
                }
            else:
                # Successful upload
                real_file_id = f"file-retry-{process_id}"
                _sync_finalize_file_id(cache, content_hash, real_file_id)
                return {
                    "process_id": process_id,
                    "status": "success",
                    "file_id": real_file_id,
                    "we_are_uploader": True,
                }
        else:
            return {
                "process_id": process_id,
                "status": "blocked",
                "file_id": file_id,
                "we_are_uploader": False,
            }

    except Exception as e:
        return {
            "process_id": process_id,
            "status": "error",
            "error": str(e),
            "we_are_uploader": False,
        }


def worker_crashing_upload(args):
    """Worker that crashes after reserving hash."""
    process_id, content_hash, db_path = args

    try:
        cache = DeduplicationCache(db_path)

        # Reserve the hash
        file_id, we_are_uploader = _sync_atomic_cache_or_get(cache, content_hash)

        if we_are_uploader:
            # Simulate some work, then crash before finalizing
            time.sleep(0.1)
            # Simulate crash by raising exception (in real world, process would terminate)
            raise RuntimeError("Simulated process crash")
        else:
            return {
                "process_id": process_id,
                "status": "blocked",
                "file_id": file_id,
            }

    except RuntimeError:
        # This simulates the process crashing - in reality, the process would terminate
        # and the PENDING entry would remain in the database
        return {
            "process_id": process_id,
            "status": "crashed",
            "we_are_uploader": True,
        }
    except Exception as e:
        return {"process_id": process_id, "status": "error", "error": str(e)}


class TestMultiProcessAtomicOperations:
    """Test atomic operations across multiple processes."""

    @pytest.fixture(autouse=True)
    def setup_and_cleanup(self):
        """Set up and clean up test database for each test."""
        setup_test_database()
        yield
        cleanup_test_database()

    async def test_multiprocess_atomic_cache_or_get(self):
        """Test that only one process wins atomic_cache_or_get across processes."""
        content_hash = "multiprocess_test_hash_" + "a" * 40

        # Create arguments for worker processes
        num_processes = 8
        worker_args = [
            (process_id, content_hash, TEST_DB_PATH)
            for process_id in range(num_processes)
        ]

        # Run processes concurrently
        with multiprocessing.Pool(processes=num_processes) as pool:
            results = pool.map(worker_atomic_cache_attempt, worker_args)

        # Analyze results
        successful_results = [r for r in results if r["status"] == "success"]
        error_results = [r for r in results if r["status"] == "error"]

        assert len(error_results) == 0, f"Unexpected errors: {error_results}"
        assert (
            len(successful_results) == num_processes
        ), "All processes should complete successfully"

        # Exactly one process should be the uploader
        uploaders = [r for r in successful_results if r["we_are_uploader"] is True]
        non_uploaders = [r for r in successful_results if r["we_are_uploader"] is False]

        assert (
            len(uploaders) == 1
        ), f"Expected exactly 1 uploader, got {len(uploaders)}: {uploaders}"
        assert (
            len(non_uploaders) == num_processes - 1
        ), f"Expected {num_processes - 1} non-uploaders"

        # All non-uploaders should see PENDING
        for result in non_uploaders:
            assert (
                result["file_id"] == "PENDING"
            ), f"Non-uploader should see PENDING, got: {result['file_id']}"

        # Verify database state
        cache = DeduplicationCache(TEST_DB_PATH)
        cached_file_id = _sync_get_file_id(cache, content_hash)
        assert (
            cached_file_id == "PENDING"
        ), "Hash should be in PENDING state after reservation"

    async def test_multiprocess_complete_workflow(self):
        """Test complete upload workflow across multiple processes."""
        content_hash = "workflow_test_hash_" + "b" * 43

        # Create arguments for worker processes
        num_processes = 6
        worker_args = [
            (process_id, content_hash, TEST_DB_PATH)
            for process_id in range(num_processes)
        ]

        # Run complete workflow in multiple processes
        with multiprocessing.Pool(processes=num_processes) as pool:
            results = pool.map(worker_complete_upload_workflow, worker_args)

        # Analyze results
        uploaded_results = [r for r in results if r["status"] == "uploaded"]
        blocked_results = [r for r in results if r["status"] == "blocked"]
        error_results = [r for r in results if r["status"] == "error"]

        assert len(error_results) == 0, f"Unexpected errors: {error_results}"
        assert (
            len(uploaded_results) == 1
        ), f"Expected exactly 1 upload, got {len(uploaded_results)}: {uploaded_results}"
        assert (
            len(blocked_results) >= num_processes - 1
        ), f"Expected at least {num_processes - 1} blocked processes"

        # Verify final database state
        cache = DeduplicationCache(TEST_DB_PATH)
        final_file_id = _sync_get_file_id(cache, content_hash)

        assert final_file_id is not None, "Final file_id should not be None"
        assert final_file_id != "PENDING", "Final file_id should not be PENDING"
        assert final_file_id.startswith(
            "file-process-"
        ), f"Unexpected final file_id format: {final_file_id}"

        # The finalized file_id should match what the uploader process reported
        uploader_file_id = uploaded_results[0]["file_id"]
        assert (
            final_file_id == uploader_file_id
        ), "Database file_id should match uploader's file_id"

    async def test_multiprocess_failure_and_recovery(self):
        """Test failure recovery workflow across multiple processes."""
        content_hash = "failure_test_hash_" + "c" * 42

        # First round: All processes attempt upload but fail
        num_processes = 5
        failing_args = [
            (process_id, content_hash, TEST_DB_PATH, True)  # should_fail=True
            for process_id in range(num_processes)
        ]

        with multiprocessing.Pool(processes=num_processes) as pool:
            first_results = pool.map(worker_failing_upload_workflow, failing_args)

        # Analyze first round results
        failed_results = [
            r for r in first_results if r["status"] == "failed_and_cleaned"
        ]
        blocked_results = [r for r in first_results if r["status"] == "blocked"]
        error_results = [r for r in first_results if r["status"] == "error"]

        assert (
            len(error_results) == 0
        ), f"Unexpected errors in first round: {error_results}"
        assert (
            len(failed_results) == 1
        ), f"Expected exactly 1 failed upload, got {len(failed_results)}"
        assert (
            len(blocked_results) >= num_processes - 1
        ), "Most processes should be blocked"

        # Verify cleanup worked - hash should be available for retry
        cache = DeduplicationCache(TEST_DB_PATH)
        cached_file_id = _sync_get_file_id(cache, content_hash)
        assert (
            cached_file_id is None
        ), "Hash should be available for retry after cleanup"

        # Second round: Retry with successful upload
        retry_args = [
            (process_id + 100, content_hash, TEST_DB_PATH, False)  # should_fail=False
            for process_id in range(num_processes)
        ]

        with multiprocessing.Pool(processes=num_processes) as pool:
            retry_results = pool.map(worker_failing_upload_workflow, retry_args)

        # Analyze retry results
        success_results = [r for r in retry_results if r["status"] == "success"]
        blocked_retry_results = [r for r in retry_results if r["status"] == "blocked"]
        retry_error_results = [r for r in retry_results if r["status"] == "error"]

        assert (
            len(retry_error_results) == 0
        ), f"Unexpected errors in retry: {retry_error_results}"
        assert (
            len(success_results) == 1
        ), f"Expected exactly 1 successful retry, got {len(success_results)}"
        assert (
            len(blocked_retry_results) >= num_processes - 1
        ), "Most retry processes should be blocked"

        # Verify final state
        final_file_id = _sync_get_file_id(cache, content_hash)
        assert (
            final_file_id is not None
        ), "Final file_id should exist after successful retry"
        assert final_file_id.startswith(
            "file-retry-"
        ), f"Unexpected retry file_id format: {final_file_id}"

    async def test_multiprocess_high_concurrency_stress(self):
        """Stress test with many processes competing for same hash."""
        content_hash = "stress_test_hash_" + "d" * 43

        # Use more processes for stress test
        num_processes = 12
        worker_args = [
            (process_id, content_hash, TEST_DB_PATH)
            for process_id in range(num_processes)
        ]

        # Run stress test
        start_time = time.time()
        with multiprocessing.Pool(processes=num_processes) as pool:
            results = pool.map(worker_complete_upload_workflow, worker_args)
        end_time = time.time()

        # Analyze stress test results
        uploaded_results = [r for r in results if r["status"] == "uploaded"]
        blocked_results = [r for r in results if r["status"] == "blocked"]
        error_results = [r for r in results if r["status"] == "error"]

        print(f"Stress test completed in {end_time - start_time:.3f} seconds")
        print(
            f"Results: {len(uploaded_results)} uploaded, {len(blocked_results)} blocked, {len(error_results)} errors"
        )

        # Critical stress test assertions
        assert len(error_results) == 0, f"Stress test had errors: {error_results}"
        assert (
            len(uploaded_results) == 1
        ), f"Stress test should have exactly 1 upload, got {len(uploaded_results)}"
        assert (
            len(blocked_results) >= num_processes - 1
        ), "Most processes should be blocked in stress test"

        # Verify consistent final state
        cache = DeduplicationCache(TEST_DB_PATH)
        final_file_id = _sync_get_file_id(cache, content_hash)
        stats = await cache.get_stats()

        assert final_file_id is not None, "Stress test should result in valid file_id"
        assert (
            final_file_id != "PENDING"
        ), "Stress test should not leave PENDING entries"
        assert (
            stats["pending_uploads"] == 0
        ), "Stress test should not leave pending uploads"

    async def test_multiprocess_mixed_hash_operations(self):
        """Test concurrent operations on multiple different hashes across processes."""
        # Use multiple different hashes
        content_hashes = [
            f"mixed_hash_{i}_" + "x" * (50 - len(str(i))) for i in range(4)
        ]

        # Create worker args with different hashes
        worker_args = []
        processes_per_hash = 3

        for hash_idx, content_hash in enumerate(content_hashes):
            for process_idx in range(processes_per_hash):
                worker_args.append(
                    (
                        hash_idx * processes_per_hash + process_idx,
                        content_hash,
                        TEST_DB_PATH,
                    )
                )

        # Run all processes concurrently
        total_processes = len(worker_args)
        with multiprocessing.Pool(processes=total_processes) as pool:
            results = pool.map(worker_complete_upload_workflow, worker_args)

        # Group results by hash
        results_by_hash = {}
        for result in results:
            # Extract hash from process workflow
            process_id = result["process_id"]
            hash_idx = process_id // processes_per_hash
            content_hash = content_hashes[hash_idx]

            if content_hash not in results_by_hash:
                results_by_hash[content_hash] = []
            results_by_hash[content_hash].append(result)

        # Verify each hash has exactly one uploader
        cache = DeduplicationCache(TEST_DB_PATH)

        for content_hash, hash_results in results_by_hash.items():
            uploaded = [r for r in hash_results if r["status"] == "uploaded"]
            blocked = [r for r in hash_results if r["status"] == "blocked"]
            errors = [r for r in hash_results if r["status"] == "error"]

            assert (
                len(uploaded) == 1
            ), f"Hash {content_hash[:20]}... should have 1 uploader, got {len(uploaded)}"
            assert (
                len(blocked) >= processes_per_hash - 1
            ), f"Hash {content_hash[:20]}... should have blocked processes"
            assert len(errors) == 0, f"Hash {content_hash[:20]}... had errors: {errors}"

            # Verify final state in database
            final_file_id = _sync_get_file_id(cache, content_hash)
            assert (
                final_file_id is not None
            ), f"Hash {content_hash[:20]}... should have final file_id"
            assert (
                final_file_id != "PENDING"
            ), f"Hash {content_hash[:20]}... should not be PENDING"


class TestProcessCrashRecovery:
    """Test recovery from process crashes during upload operations."""

    @pytest.fixture(autouse=True)
    def setup_and_cleanup(self):
        """Set up and clean up test database for each test."""
        setup_test_database()
        yield
        cleanup_test_database()

    @pytest.mark.skipif(
        os.name == "nt", reason="Signal handling not reliable on Windows"
    )
    async def test_process_crash_during_upload(self):
        """Test recovery when a process crashes after reserving but before finalizing."""
        content_hash = "crash_test_hash_" + "e" * 45

        # First: Run the crashing process
        crash_args = [(0, content_hash, TEST_DB_PATH)]

        with multiprocessing.Pool(processes=1) as pool:
            crash_results = pool.map(worker_crashing_upload, crash_args)

        # Verify crash occurred and left PENDING entry
        cache = DeduplicationCache(TEST_DB_PATH)
        cached_file_id = _sync_get_file_id(cache, content_hash)

        assert cached_file_id == "PENDING", "Crashed process should leave PENDING entry"
        assert crash_results[0]["status"] == "crashed", "Process should have crashed"

        # Now simulate retry attempts by other processes
        retry_args = [
            (process_id + 10, content_hash, TEST_DB_PATH) for process_id in range(3)
        ]

        # These should all be blocked by the stale PENDING entry
        with multiprocessing.Pool(processes=3) as pool:
            retry_results = pool.map(worker_atomic_cache_attempt, retry_args)

        # All retries should be blocked by PENDING entry
        for result in retry_results:
            assert result["status"] == "success", "Retry attempts should succeed"
            assert result["we_are_uploader"] is False, "Retries should be blocked"
            assert result["file_id"] == "PENDING", "Retries should see PENDING"

        # Manual cleanup of stale PENDING entry (simulates cleanup task)
        await cache.cleanup_failed_upload(content_hash)

        # Verify cleanup worked
        cached_file_id = _sync_get_file_id(cache, content_hash)
        assert cached_file_id is None, "Cleanup should remove PENDING entry"

        # Now a new attempt should succeed
        final_attempt_args = [(99, content_hash, TEST_DB_PATH)]

        with multiprocessing.Pool(processes=1) as pool:
            final_results = pool.map(
                worker_complete_upload_workflow, final_attempt_args
            )

        assert (
            final_results[0]["status"] == "uploaded"
        ), "Final attempt should succeed after cleanup"

        # Verify final state
        final_file_id = _sync_get_file_id(cache, content_hash)
        assert final_file_id is not None, "Should have valid file_id after recovery"
        assert final_file_id != "PENDING", "Should not be PENDING after recovery"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
