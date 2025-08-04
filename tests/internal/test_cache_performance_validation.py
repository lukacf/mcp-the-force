"""Performance validation tests for DeduplicationCache atomic operations.

These tests ensure that the atomic operations maintain good performance
characteristics while providing race condition prevention.

Focus areas:
- Performance under normal (non-concurrent) usage
- Performance degradation under high concurrency
- Database lock contention timing
- Memory usage patterns during concurrent operations
"""

import pytest
import time
import threading
import tempfile
import asyncio
from pathlib import Path

from mcp_the_force.dedup.simple_cache import DeduplicationCache


@pytest.fixture
def performance_cache():
    """Create a temporary cache for performance testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    cache = DeduplicationCache(db_path)

    yield cache

    # Cleanup
    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass


class TestPerformanceBaseline:
    """Test baseline performance characteristics."""

    async def test_single_threaded_performance(self, performance_cache):
        """Test performance of atomic operations in single-threaded scenario."""
        cache = performance_cache

        # Test atomic_cache_or_get performance
        num_operations = 100
        content_hashes = [f"hash_{i}_" + "x" * 55 for i in range(num_operations)]

        start_time = time.time()

        for content_hash in content_hashes:
            file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
            assert we_are_uploader is True

            # Simulate finalization
            await cache.finalize_file_id(content_hash, f"file-{content_hash[:8]}")

        end_time = time.time()
        total_time = end_time - start_time
        ops_per_second = num_operations / total_time

        print(f"Single-threaded performance: {ops_per_second:.1f} operations/second")
        print(
            f"Average time per operation: {(total_time * 1000 / num_operations):.2f}ms"
        )

        # Performance assertion - should handle at least 100 ops/second
        assert (
            ops_per_second > 100
        ), f"Performance too slow: {ops_per_second:.1f} ops/sec"

        # Verify all operations completed correctly
        for content_hash in content_hashes:
            cached_file_id = await cache.get_file_id(content_hash)
            assert cached_file_id is not None
            assert cached_file_id != "PENDING"

    async def test_read_operation_performance(self, performance_cache):
        """Test performance of read operations (get_file_id, get_store_id)."""
        cache = performance_cache

        # Populate cache with data
        num_entries = 1000
        for i in range(num_entries):
            content_hash = f"read_test_hash_{i}_" + "x" * 45
            await cache.cache_file(content_hash, f"file-{i}")

            fileset_hash = f"read_test_fileset_{i}_" + "x" * 40
            await cache.cache_store(fileset_hash, f"store-{i}", "openai")

        # Test read performance
        start_time = time.time()

        for i in range(num_entries):
            content_hash = f"read_test_hash_{i}_" + "x" * 45
            file_id = await cache.get_file_id(content_hash)
            assert file_id == f"file-{i}"

            fileset_hash = f"read_test_fileset_{i}_" + "x" * 40
            store_info = await cache.get_store_id(fileset_hash)
            assert store_info["store_id"] == f"store-{i}"

        end_time = time.time()
        total_time = end_time - start_time
        reads_per_second = (num_entries * 2) / total_time  # 2 reads per iteration

        print(f"Read performance: {reads_per_second:.1f} reads/second")
        print(f"Average read time: {(total_time * 1000 / (num_entries * 2)):.3f}ms")

        # Read operations should be very fast
        assert (
            reads_per_second > 1000
        ), f"Read performance too slow: {reads_per_second:.1f} reads/sec"


class TestConcurrencyPerformance:
    """Test performance characteristics under concurrency."""

    async def test_concurrent_different_hashes_performance(self, performance_cache):
        """Test performance when many threads work on different hashes simultaneously."""
        cache = performance_cache

        async def process_unique_hash(thread_id):
            """Process a unique hash for this thread."""
            content_hash = f"concurrent_hash_{thread_id}_" + "x" * 45

            start_time = time.time()

            # Atomic operation
            file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)
            assert we_are_uploader is True

            # Simulate some work
            time.sleep(0.001)

            # Finalize
            await cache.finalize_file_id(content_hash, f"file-{thread_id}")

            end_time = time.time()
            return end_time - start_time

        # Run concurrent operations on different hashes
        num_threads = 20
        start_time = time.time()

        tasks = [process_unique_hash(i) for i in range(num_threads)]
        individual_times = await asyncio.gather(*tasks)

        total_time = time.time() - start_time

        avg_individual_time = sum(individual_times) / len(individual_times)
        ops_per_second = num_threads / total_time

        print(f"Concurrent different hashes: {ops_per_second:.1f} ops/second total")
        print(
            f"Average individual operation time: {(avg_individual_time * 1000):.2f}ms"
        )
        print(f"Total wall clock time: {(total_time * 1000):.2f}ms")

        # Should achieve good concurrency with different hashes
        assert (
            ops_per_second > 50
        ), f"Concurrent performance too slow: {ops_per_second:.1f} ops/sec"

        # Individual operations shouldn't be significantly slower than single-threaded
        assert (
            avg_individual_time < 0.1
        ), f"Individual operations too slow under concurrency: {avg_individual_time:.3f}s"

    async def test_contention_performance_same_hash(self, performance_cache):
        """Test performance when many threads compete for the same hash."""
        cache = performance_cache
        content_hash = "contention_test_hash_" + "x" * 44

        results = []

        async def compete_for_hash(thread_id):
            """Compete for the same hash."""
            start_time = time.time()

            file_id, we_are_uploader = await cache.atomic_cache_or_get(content_hash)

            if we_are_uploader:
                # Winner - do the work
                time.sleep(0.01)  # Simulate upload
                await cache.finalize_file_id(content_hash, f"file-winner-{thread_id}")
                status = "winner"
            else:
                # Loser - should be fast
                status = "loser"

            end_time = time.time()
            return (thread_id, status, end_time - start_time)

        # Run many threads competing for same hash
        num_threads = 15
        start_time = time.time()

        tasks = [compete_for_hash(i) for i in range(num_threads)]
        results = await asyncio.gather(*tasks)

        total_time = time.time() - start_time

        # Analyze results
        winners = [r for r in results if r[1] == "winner"]
        losers = [r for r in results if r[1] == "loser"]

        winner_time = winners[0][2] if winners else 0
        avg_loser_time = sum(r[2] for r in losers) / len(losers) if losers else 0

        print(f"Hash contention test - {len(winners)} winners, {len(losers)} losers")
        print(f"Winner took: {(winner_time * 1000):.2f}ms")
        print(f"Average loser time: {(avg_loser_time * 1000):.2f}ms")
        print(f"Total wall clock time: {(total_time * 1000):.2f}ms")

        # Verify correctness
        assert len(winners) == 1, f"Expected 1 winner, got {len(winners)}"
        assert (
            len(losers) >= num_threads - 1
        ), f"Expected at least {num_threads - 1} losers"

        # Performance assertions
        assert avg_loser_time < 0.05, f"Losers took too long: {avg_loser_time:.3f}s"
        assert (
            total_time < 1.0
        ), f"Overall contention resolution took too long: {total_time:.3f}s"

    async def test_database_lock_timeout_performance(self, performance_cache):
        """Test performance characteristics during database lock scenarios."""
        cache = performance_cache

        lock_held_time = 0.5  # Hold lock for 500ms
        measurements = []

        def hold_long_transaction():
            """Hold a database lock for extended period."""
            nonlocal lock_held_time
            conn = cache._get_connection()
            try:
                start_time = time.time()
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT OR IGNORE INTO file_cache (content_hash, file_id, created_at) VALUES (?, ?, ?)",
                    ("lock_holder_hash", "PENDING", int(time.time())),
                )

                # Hold the lock
                time.sleep(lock_held_time)

                conn.commit()
                end_time = time.time()
                measurements.append(("lock_holder", end_time - start_time))

            except Exception as e:
                conn.rollback()
                measurements.append(("lock_holder_error", str(e)))
            finally:
                conn.close()

        async def attempt_during_lock(thread_id):
            """Attempt operation while lock is held."""
            try:
                start_time = time.time()
                file_id, we_are_uploader = await cache.atomic_cache_or_get(
                    f"test_hash_{thread_id}"
                )
                end_time = time.time()

                return (thread_id, "success", end_time - start_time, we_are_uploader)

            except Exception as e:
                end_time = time.time()
                return (thread_id, "error", end_time - start_time, str(e))

        # Start lock holder
        lock_thread = threading.Thread(target=hold_long_transaction)
        lock_thread.start()

        # Give lock holder time to acquire lock
        time.sleep(0.1)

        # Start competing tasks
        num_competing = 5
        tasks = [attempt_during_lock(i) for i in range(num_competing)]
        competing_results = await asyncio.gather(*tasks)

        # Wait for lock holder to finish
        lock_thread.join()

        # Analyze performance during lock contention
        successful_ops = [r for r in competing_results if r[1] == "success"]
        failed_ops = [r for r in competing_results if r[1] == "error"]

        if successful_ops:
            avg_success_time = sum(r[2] for r in successful_ops) / len(successful_ops)
            max_success_time = max(r[2] for r in successful_ops)

            print("Lock contention performance:")
            print(f"  Successful operations: {len(successful_ops)}")
            print(f"  Failed operations: {len(failed_ops)}")
            print(f"  Average success time: {(avg_success_time * 1000):.2f}ms")
            print(f"  Max success time: {(max_success_time * 1000):.2f}ms")

            # Operations should complete within reasonable time even during lock contention
            # (SQLite busy_timeout is 30 seconds, but operations should complete much faster)
            assert (
                max_success_time < 5.0
            ), f"Operations took too long during lock contention: {max_success_time:.3f}s"

        # At least some operations should succeed (after lock is released)
        assert (
            len(successful_ops) > 0
        ), "No operations succeeded during lock contention test"


class TestMemoryPerformance:
    """Test memory usage characteristics during concurrent operations."""

    async def test_stats_performance_with_large_cache(self, performance_cache):
        """Test performance of cache statistics with large number of entries."""
        cache = performance_cache

        # Populate cache with many entries
        num_entries = 5000

        populate_start = time.time()
        for i in range(num_entries):
            await cache.cache_file(f"large_cache_file_{i}_" + "x" * 40, f"file-{i}")
            if i % 2 == 0:  # Add some store entries too
                await cache.cache_store(
                    f"large_cache_store_{i}_" + "x" * 40, f"store-{i}", "openai"
                )
        populate_time = time.time() - populate_start

        print(f"Populated cache with {num_entries} entries in {populate_time:.2f}s")

        # Test stats performance
        stats_times = []
        for _ in range(10):
            start_time = time.time()
            stats = await cache.get_stats()
            end_time = time.time()
            stats_times.append(end_time - start_time)

        avg_stats_time = sum(stats_times) / len(stats_times)

        print(f"Cache stats: {stats}")
        print(f"Average stats query time: {(avg_stats_time * 1000):.2f}ms")

        # Stats should be fast even with large cache
        assert avg_stats_time < 0.1, f"Stats query too slow: {avg_stats_time:.3f}s"
        assert stats["file_count"] == num_entries
        assert stats["store_count"] >= num_entries // 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
