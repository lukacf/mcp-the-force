"""Test unified session cache with async operations."""

import pytest
import tempfile
import os
import asyncio
import time

from mcp_the_force.unified_session_cache import (
    _SQLiteUnifiedSessionCache,
    unified_session_cache,
    UnifiedSession,
)


@pytest.mark.asyncio
async def test_basic_set_get():
    """Test basic set and get operations."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteUnifiedSessionCache(db_path=db_path, ttl=3600)

        # Set a response ID
        # Note: Session key is (project, session_id)
        session = UnifiedSession(
            project="test-project",
            session_id="test_session",
            updated_at=int(time.time()),
            provider_metadata={"response_id": "test_response"},
        )
        await cache.set_session(session)

        # Get it back
        result = await cache.get_session("test-project", "test_session")
        assert result is not None
        assert result.provider_metadata.get("response_id") == "test_response"

        # Non-existent session returns None
        result = await cache.get_session("test-project", "nonexistent")
        assert result is None

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_persistence():
    """Test that data persists across cache instances."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        # First instance
        cache1 = _SQLiteUnifiedSessionCache(db_path=db_path, ttl=3600)
        session = UnifiedSession(
            project="test-project",
            session_id="persist_test",
            updated_at=int(time.time()),
            provider_metadata={"response_id": "persist_value"},
        )
        await cache1.set_session(session)
        cache1.close()

        # Second instance should see the data
        cache2 = _SQLiteUnifiedSessionCache(db_path=db_path, ttl=3600)
        result = await cache2.get_session("test-project", "persist_test")
        assert result is not None
        assert result.provider_metadata.get("response_id") == "persist_value"
        cache2.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_expiration(monkeypatch):
    """Test TTL expiration."""
    from tests.conftest import mock_clock

    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteUnifiedSessionCache(db_path=db_path, ttl=1)

        with mock_clock(monkeypatch) as tick:
            session = UnifiedSession(
                project="test-project",
                session_id="expire_test",
                updated_at=int(time.time()),
                provider_metadata={"response_id": "expire_value"},
            )
            await cache.set_session(session)

            # Should exist immediately
            result = await cache.get_session("test-project", "expire_test")
            assert result is not None
            assert result.provider_metadata.get("response_id") == "expire_value"

            # Advance virtual clock past TTL
            tick(1.1)

            # Should be expired
            result = await cache.get_session("test-project", "expire_test")
            assert result is None

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_concurrent_access():
    """Test concurrent operations work correctly."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteUnifiedSessionCache(db_path=db_path, ttl=3600)

        async def write_many(prefix, count):
            for i in range(count):
                session = UnifiedSession(
                    project="test-project",
                    session_id=f"{prefix}_{i}",
                    updated_at=int(time.time()),
                    provider_metadata={"value": f"value_{i}"},
                )
                await cache.set_session(session)

        async def read_many(prefix, count):
            results = []
            for i in range(count):
                result = await cache.get_session("test-project", f"{prefix}_{i}")
                results.append(result)
            return results

        # Write concurrently
        await asyncio.gather(
            write_many("group1", 5),
            write_many("group2", 5),
            write_many("group3", 5),
        )

        # Read concurrently
        results = await asyncio.gather(
            read_many("group1", 5),
            read_many("group2", 5),
            read_many("group3", 5),
        )

        # Verify all reads succeeded
        for group_results in results:
            assert all(r is not None for r in group_results)

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_long_ids_rejected():
    """Test that overly long IDs are rejected."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    try:
        cache = _SQLiteUnifiedSessionCache(db_path=db_path, ttl=3600)

        # Session ID too long
        with pytest.raises(ValueError, match="session_id too long"):
            session = UnifiedSession(
                project="test-project",
                session_id="x" * 1025,
                updated_at=int(time.time()),
            )
            await cache.set_session(session)

        with pytest.raises(ValueError, match="session_id too long"):
            await cache.get_session("test-project", "x" * 1025)

        cache.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_proxy_interface():
    """Test the global proxy interface."""
    import uuid

    # Use unique session IDs for each test to avoid interference
    proxy_session = f"proxy_test_{uuid.uuid4()}"
    history_session = f"history_test_{uuid.uuid4()}"
    append_session = f"append_test_{uuid.uuid4()}"

    # The unified_session_cache proxy should work with await
    # Note: Session key is (project, session_id) - no tool in key
    await unified_session_cache.set_response_id(
        "test-project", proxy_session, "proxy_value"
    )
    result = await unified_session_cache.get_response_id("test-project", proxy_session)
    assert result == "proxy_value"

    # Test history methods
    await unified_session_cache.set_history(
        "test-project",
        history_session,
        [{"role": "user", "content": "Hello"}],
    )
    history = await unified_session_cache.get_history("test-project", history_session)
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"

    # Test append methods
    await unified_session_cache.append_chat_message(
        "test-project", append_session, "assistant", "Hi there!"
    )
    history = await unified_session_cache.get_history("test-project", append_session)
    assert len(history) == 1
    assert history[0]["role"] == "assistant"
    assert history[0]["content"] == "Hi there!"

    # Close should work
    unified_session_cache.close()


@pytest.mark.asyncio
async def test_session_metadata():
    """Test provider metadata storage."""
    session_id = "metadata_test"

    # Set multiple metadata fields
    # Use metadata methods instead of direct session access
    # Note: Session key is (project, session_id) - no tool in key
    await unified_session_cache.set_metadata(
        "test-project", session_id, "response_id", "resp_123"
    )
    await unified_session_cache.set_metadata(
        "test-project", session_id, "api_format", "responses"
    )
    await unified_session_cache.set_metadata(
        "test-project", session_id, "deployment_id", "deploy_456"
    )

    # Get back and verify
    response_id = await unified_session_cache.get_metadata(
        "test-project", session_id, "response_id"
    )
    api_format = await unified_session_cache.get_metadata(
        "test-project", session_id, "api_format"
    )
    deployment_id = await unified_session_cache.get_metadata(
        "test-project", session_id, "deployment_id"
    )
    assert response_id == "resp_123"
    assert api_format == "responses"
    assert deployment_id == "deploy_456"


@pytest.mark.asyncio
class TestSessionCacheSummary:
    """Tests for summary caching functionality."""

    async def test_get_summary_for_non_existent_session(self, isolate_test_databases):
        """Test get_summary returns None for non-existent session."""
        # Note: Session key is (project, session_id) - no tool in key
        result = await unified_session_cache.get_summary(
            "test-project", "non-existent-session"
        )
        assert result is None

    async def test_set_and_get_summary(self, isolate_test_databases):
        """Test setting and getting a summary."""
        project = "test-project"
        session_id = "summary-test"
        summary = "This is a test summary of the conversation."

        # Set the summary
        await unified_session_cache.set_summary(project, session_id, summary)

        # Get it back
        result = await unified_session_cache.get_summary(project, session_id)
        assert result == summary

    async def test_set_history_invalidates_summary(self, isolate_test_databases):
        """Test that updating session history invalidates the summary."""
        project = "test-project"
        session_id = "invalidation-test"

        # Create a session and set a summary
        await unified_session_cache.set_history(
            project, session_id, [{"role": "user", "content": "Initial message"}]
        )
        await unified_session_cache.set_summary(project, session_id, "Initial summary")

        # Verify summary exists
        summary = await unified_session_cache.get_summary(project, session_id)
        assert summary == "Initial summary"

        # Update the session (add new message)
        await unified_session_cache.set_history(
            project,
            session_id,
            [
                {"role": "user", "content": "Initial message"},
                {"role": "assistant", "content": "Response"},
            ],
        )

        # Summary should be invalidated (None)
        summary = await unified_session_cache.get_summary(project, session_id)
        assert summary is None
