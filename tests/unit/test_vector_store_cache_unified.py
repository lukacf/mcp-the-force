"""Unit tests for the unified VectorStoreCache with new schema."""

import pytest
import time
from mcp_the_force.vector_store_cache import VectorStoreCache


@pytest.mark.asyncio
class TestVectorStoreCacheUnified:
    """Unit tests for the unified VectorStoreCache."""

    @pytest.fixture
    async def cache(self, tmp_path):
        """Create a VectorStoreCache instance for testing."""
        db_path = tmp_path / "test_vector_stores_unified.db"
        cache = VectorStoreCache(
            str(db_path), ttl=120, purge_probability=0.0
        )  # Disable probabilistic cleanup
        yield cache
        # Cleanup
        cache.close()

    async def test_name_session_id_exclusivity(self, cache):
        """Test that name and session_id are mutually exclusive."""
        vector_store_id = "vs_test123"

        # Test: Cannot have both name and session_id
        with pytest.raises(
            ValueError, match="Exactly one of session_id or name must be provided"
        ):
            await cache.register_store(
                vector_store_id=vector_store_id,
                provider="openai",
                session_id="test-session",
                name="test-name",
            )

        # Test: Must have at least one
        with pytest.raises(
            ValueError, match="Exactly one of session_id or name must be provided"
        ):
            await cache.register_store(
                vector_store_id=vector_store_id, provider="openai"
            )

    async def test_session_store_creation(self, cache):
        """Test creating and retrieving a session-based store."""
        session_id = "test-session-456"
        vector_store_id = "vs_session456"

        # Register a session store
        await cache.register_store(
            vector_store_id=vector_store_id,
            provider="openai",
            session_id=session_id,
            ttl_seconds=300,  # 5 minutes
        )

        # Retrieve by session_id
        store = await cache.get_store(session_id=session_id)
        assert store is not None
        assert store["vector_store_id"] == vector_store_id
        assert store["session_id"] == session_id
        assert store["name"] is None
        assert store["is_protected"] == 0
        assert store["expires_at"] is not None

    async def test_named_store_creation(self, cache):
        """Test creating and retrieving a named store."""
        name = "project-conversations-001"
        vector_store_id = "vs_memory001"

        # Register a named store
        await cache.register_store(
            vector_store_id=vector_store_id,
            provider="openai",
            name=name,
            protected=True,
        )

        # Retrieve by name
        store = await cache.get_store(name=name)
        assert store is not None
        assert store["vector_store_id"] == vector_store_id
        assert store["name"] == name
        assert store["session_id"] is None
        assert store["is_protected"] == 1
        assert store["expires_at"] is None  # Protected stores don't expire

    async def test_set_inactive(self, cache):
        """Test marking a store as inactive."""
        name = "project-conversations-001"
        vector_store_id = "vs_inactive001"

        # Create an active store
        await cache.register_store(
            vector_store_id=vector_store_id,
            provider="openai",
            name=name,
            protected=True,
        )

        # Verify it's active
        store = await cache.get_store(name=name)
        assert store["is_active"] == 1

        # Mark as inactive
        success = await cache.set_inactive(vector_store_id)
        assert success is True

        # Verify it's no longer found (since get_store only returns active stores)
        store = await cache.get_store(name=name)
        assert store is None

    async def test_rollover_from_relationships(self, cache):
        """Test rollover_from tracking for memory stores."""
        # Create first store
        old_store_id = "vs_old001"
        old_name = "project-conversations-001"
        await cache.register_store(
            vector_store_id=old_store_id,
            provider="openai",
            name=old_name,
            protected=True,
        )

        # Create new store with rollover_from
        new_store_id = "vs_new001"
        new_name = "project-conversations-002"
        await cache.register_store(
            vector_store_id=new_store_id,
            provider="openai",
            name=new_name,
            protected=True,
            rollover_from=old_store_id,
        )

        # Verify rollover relationship
        new_store = await cache.get_store(name=new_name)
        assert new_store["rollover_from"] == old_store_id

    async def test_provider_metadata(self, cache):
        """Test storing and retrieving provider metadata."""
        vector_store_id = "vs_metadata001"
        session_id = "test-metadata"
        metadata = {
            "index_type": "hnsw",
            "dimensions": 1536,
            "m": 16,
            "ef_construction": 200,
        }

        # Register with metadata
        await cache.register_store(
            vector_store_id=vector_store_id,
            provider="hnsw",
            session_id=session_id,
            provider_metadata=metadata,
        )

        # Retrieve and verify
        store = await cache.get_store(session_id=session_id)
        assert store["provider"] == "hnsw"
        # provider_metadata is already deserialized by get_store
        assert store["provider_metadata"] == metadata

    async def test_protected_stores_no_expiry(self, cache):
        """Test that protected stores don't have expiry times."""
        # Create protected named store
        await cache.register_store(
            vector_store_id="vs_protected",
            provider="openai",
            name="project-protected",
            protected=True,
        )

        # Create unprotected session store
        await cache.register_store(
            vector_store_id="vs_unprotected",
            provider="openai",
            session_id="session-unprotected",
            protected=False,
        )

        # Verify protected store has no expiry
        protected = await cache.get_store(name="project-protected")
        assert protected["is_protected"] == 1
        assert protected["expires_at"] is None

        # Verify unprotected store has expiry
        unprotected = await cache.get_store(session_id="session-unprotected")
        assert unprotected["is_protected"] == 0
        assert unprotected["expires_at"] is not None

    async def test_get_store_flexible_lookup(self, cache):
        """Test flexible store lookup by various identifiers."""
        vector_store_id = "vs_flexible001"
        session_id = "test-flexible"

        await cache.register_store(
            vector_store_id=vector_store_id, provider="openai", session_id=session_id
        )

        # Lookup by session_id
        store1 = await cache.get_store(session_id=session_id)
        assert store1["vector_store_id"] == vector_store_id

        # Lookup by vector_store_id
        store2 = await cache.get_store(vector_store_id=vector_store_id)
        assert store2["session_id"] == session_id

        # Both should return the same store
        assert store1 == store2

    async def test_cleanup_respects_protected_flag(
        self, cache, virtual_clock, monkeypatch
    ):
        """Test that cleanup doesn't remove protected stores."""
        # Patch time
        monkeypatch.setattr(time, "time", virtual_clock.time)

        # Create unprotected session store
        await cache.register_store(
            vector_store_id="vs_temp001",
            provider="openai",
            session_id="temp-session",
            protected=False,
            ttl_seconds=60,  # 1 minute
        )

        # Create protected named store
        await cache.register_store(
            vector_store_id="vs_perm001",
            provider="openai",
            name="permanent-store",
            protected=True,
        )

        # Advance time past TTL
        virtual_clock.advance_time(120)  # 2 minutes

        # Get expired stores
        expired = await cache.get_expired_stores()

        # Only unprotected store should be expired
        assert len(expired) == 1
        assert expired[0]["vector_store_id"] == "vs_temp001"
        # get_expired_stores already filters by is_protected=0, so all results are unprotected
