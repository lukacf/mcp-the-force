"""Unit tests for the VectorStoreCache."""

import pytest
import time
from mcp_the_force.vector_store_cache import VectorStoreCache


@pytest.mark.asyncio
class TestVectorStoreCache:
    """Unit tests for the VectorStoreCache."""

    @pytest.fixture
    async def cache(self, tmp_path):
        """Create a VectorStoreCache instance for testing."""
        db_path = tmp_path / "test_vector_stores.db"
        cache = VectorStoreCache(
            str(db_path), ttl=120, purge_probability=0.0
        )  # Disable probabilistic cleanup
        yield cache
        # Cleanup
        cache.close()

    async def test_add_and_get_store(self, cache):
        """Verify that a store can be added and retrieved correctly."""
        # GIVEN a new VectorStoreCache instance
        session_id = "test-session-123"
        vector_store_id = "vs_abc123"

        # First check that no store exists
        result, reused = await cache.get_or_create_placeholder(session_id)
        assert result is None
        assert reused is False

        # WHEN a new store is added
        await cache.register_store(session_id, vector_store_id, provider="openai")

        # THEN the same store can be retrieved by its session_id
        result, reused = await cache.get_or_create_placeholder(session_id)
        assert result == vector_store_id
        assert reused is True

        # AND a non-existent session_id returns None
        result, reused = await cache.get_or_create_placeholder("non-existent")
        assert result is None
        assert reused is False

    async def test_lease_renewal(self, cache, virtual_clock, monkeypatch):
        """Verify that renewing a lease updates the expires_at timestamp."""
        # Patch time functions
        monkeypatch.setattr(time, "time", virtual_clock.time)

        # GIVEN a store is added with an initial expiry
        session_id = "test-session-456"
        vector_store_id = "vs_def456"

        await cache.register_store(session_id, vector_store_id)

        # Advance time by 60 seconds
        virtual_clock.advance_time(60)

        # WHEN renew_lease() is called for that session
        renewed = await cache.renew_lease(session_id)
        assert renewed is True

        # THEN the expires_at timestamp in the database is updated to a future value
        # The store should still be retrievable after the original TTL would have expired
        virtual_clock.advance_time(65)  # Total 125 seconds, past original 120s TTL

        result, reused = await cache.get_or_create_placeholder(session_id)
        assert result == vector_store_id  # Still found because lease was renewed
        assert reused is True

    async def test_ttl_expiry(self, virtual_clock, monkeypatch, tmp_path):
        """Verify that expired stores are correctly identified and purged."""
        # Patch time functions
        monkeypatch.setattr(time, "time", virtual_clock.time)

        # GIVEN a cache with a short TTL (e.g., 2 seconds)
        db_path = tmp_path / "test_ttl_vector_stores.db"
        cache = VectorStoreCache(str(db_path), ttl=2, purge_probability=0.0)

        try:
            # AND a store is added at virtual time T
            session_id = "test-session-789"
            vector_store_id = "vs_ghi789"
            await cache.register_store(session_id, vector_store_id)

            # Verify it's initially retrievable
            result, reused = await cache.get_or_create_placeholder(session_id)
            assert result == vector_store_id

            # WHEN the virtual_clock is advanced by 3 seconds
            virtual_clock.advance_time(3)

            # THEN get_expired_stores() returns this store's ID
            expired = await cache.get_expired_stores()
            assert len(expired) == 1
            assert expired[0]["session_id"] == session_id
            assert expired[0]["vector_store_id"] == vector_store_id

            # AND get_store() for this session returns None (as it's considered expired)
            result, reused = await cache.get_or_create_placeholder(session_id)
            assert result is None
            assert reused is False
        finally:
            cache.close()

    async def test_protected_stores_are_ignored_by_cleanup(
        self, cache, virtual_clock, monkeypatch
    ):
        """Verify that protected stores are never returned by get_expired_stores."""
        # Patch time functions
        monkeypatch.setattr(time, "time", virtual_clock.time)

        # GIVEN two stores, one with protected=0 and one with protected=1
        normal_session = "normal-session"
        protected_session = "protected-session"

        await cache.register_store(normal_session, "vs_normal", protected=False)
        await cache.register_store(protected_session, "vs_protected", protected=True)

        # Advance time to make both expire
        virtual_clock.advance_time(200)  # Well past the 120s TTL

        # WHEN get_expired_stores() is called
        expired = await cache.get_expired_stores()

        # THEN only the ID of the store with protected=0 is returned
        assert len(expired) == 1
        assert expired[0]["session_id"] == normal_session

        # The protected store should still be retrievable even though it's past TTL
        # (protected stores ignore TTL for cleanup purposes)
        stats = await cache.get_stats()
        assert stats["protected"] == 1

    async def test_remove_store(self, cache):
        """Verify that remove_store correctly deletes entries."""
        # GIVEN a store exists
        session_id = "test-remove"
        await cache.register_store(session_id, "vs_remove123")

        # Verify it exists
        result, _ = await cache.get_or_create_placeholder(session_id)
        assert result is not None

        # WHEN remove_store is called
        removed = await cache.remove_store(session_id)
        assert removed is True

        # THEN the store is no longer retrievable
        result, _ = await cache.get_or_create_placeholder(session_id)
        assert result is None

        # AND calling remove again returns False
        removed = await cache.remove_store(session_id)
        assert removed is False

    async def test_cleanup_orphaned(self, cache, virtual_clock, monkeypatch):
        """Verify that cleanup_orphaned removes very old entries."""
        # Patch time functions
        monkeypatch.setattr(time, "time", virtual_clock.time)

        # GIVEN entries created at different times
        await cache.register_store("ancient", "vs_ancient")

        # Advance time by 29 days (not yet orphaned)
        virtual_clock.advance_time(29 * 24 * 60 * 60)
        await cache.register_store("medium", "vs_medium")

        # Advance time by 2 more days (31 days total for first entry)
        virtual_clock.advance_time(2 * 24 * 60 * 60)

        # Check stats before cleanup
        stats_before = await cache.get_stats()

        # WHEN cleanup_orphaned is called
        count = await cache.cleanup_orphaned()

        # THEN only the 31-day old entry is removed
        assert count == 1

        # Check stats after cleanup
        stats_after = await cache.get_stats()
        assert stats_after["total"] == stats_before["total"] - 1

        # The ancient store should be gone from the database entirely
        # Check by trying to get expired stores (which should include all stores since we're 31 days in the future)
        expired = await cache.get_expired_stores()
        # Should only find the medium store in expired list
        assert len(expired) == 1
        assert expired[0]["session_id"] == "medium"

    async def test_get_stats(self, cache, virtual_clock, monkeypatch):
        """Verify that get_stats returns correct counts."""
        # Patch time functions
        monkeypatch.setattr(time, "time", virtual_clock.time)

        # GIVEN various stores in different states
        await cache.register_store("active1", "vs_active1")
        await cache.register_store("active2", "vs_active2")
        await cache.register_store("protected1", "vs_protected1", protected=True)

        # Advance time to expire some stores
        virtual_clock.advance_time(150)  # Past 120s TTL

        await cache.register_store("active3", "vs_active3")  # New active store

        # WHEN get_stats is called
        stats = await cache.get_stats()

        # THEN it returns correct counts
        assert stats["total"] == 4  # All stores
        assert (
            stats["active"] == 1
        )  # Only active3 (protected1 is expired but protected)
        assert (
            stats["expired"] == 2
        )  # active1 and active2 (protected stores don't count as expired)
        assert stats["protected"] == 1  # protected1

    async def test_concurrent_access(self, cache):
        """Verify that concurrent operations work correctly."""
        import asyncio

        # GIVEN multiple concurrent operations
        session_ids = [f"concurrent-{i}" for i in range(10)]

        # WHEN multiple stores are registered concurrently
        tasks = []
        for i, session_id in enumerate(session_ids):
            tasks.append(cache.register_store(session_id, f"vs_concurrent_{i}"))

        await asyncio.gather(*tasks)

        # THEN all stores are retrievable
        for session_id in session_ids:
            result, reused = await cache.get_or_create_placeholder(session_id)
            assert result is not None
            assert reused is True

    async def test_session_id_validation(self, cache):
        """Verify that invalid session IDs are rejected."""
        # Test very long session ID
        long_id = "x" * 1025  # Over 1024 character limit
        with pytest.raises(ValueError, match="session_id too long"):
            await cache.register_store(long_id, "vs_test")

        # Valid session IDs should work
        await cache.register_store("valid-session-123", "vs_test")
        await cache.register_store("", "vs_empty")  # Empty is allowed by base class
        await cache.register_store(
            "   ", "vs_spaces"
        )  # Spaces are allowed by base class
