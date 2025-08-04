"""Simple tests to validate the transactional cache pollution fix."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from mcp_the_force.vectorstores.openai.openai_vectorstore import OpenAIVectorStore
from mcp_the_force.vectorstores.protocol import VSFile
from mcp_the_force.dedup.simple_cache import SimpleVectorStoreCache
from mcp_the_force.dedup.hashing import compute_content_hash


@pytest.fixture
def temp_cache():
    """Create a temporary cache database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    cache = SimpleVectorStoreCache(db_path)
    yield cache

    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture
def test_file():
    """Create a test VSFile."""
    return VSFile(path="test.py", content="def hello(): pass")


@pytest.fixture
def mock_client():
    """Create a mock OpenAI client."""
    client = AsyncMock()

    upload_response = Mock()
    upload_response.id = "file-abc123"
    client.files.create = AsyncMock(return_value=upload_response)

    client.vector_stores.file_batches.create_and_poll = AsyncMock(return_value=None)
    client.files.delete = AsyncMock(return_value=None)

    return client


class TestTransactionalComponents:
    """Test individual transactional components."""

    async def test_upload_files_transactional_basic(
        self, temp_cache, test_file, mock_client
    ):
        """Test basic transactional upload functionality."""
        vector_store = OpenAIVectorStore(mock_client, "vs-test", "test-store")
        content_hash = compute_content_hash(test_file.content)

        # Reserve cache entry as if we won the race
        file_id, we_are_uploader = temp_cache.atomic_cache_or_get(content_hash)
        assert we_are_uploader is True
        assert file_id is None

        # Verify PENDING state
        cached_file_id = temp_cache.get_file_id(content_hash)
        assert cached_file_id == "PENDING"

        # Test transactional upload (should not finalize cache)
        newly_uploaded = await vector_store._upload_files_transactional(
            [test_file], temp_cache
        )

        # Verify upload happened
        assert len(newly_uploaded) == 1
        assert newly_uploaded[0][0] == content_hash
        assert newly_uploaded[0][1] == "file-abc123"

        # Cache should still be PENDING (not finalized yet)
        cached_file_id = temp_cache.get_file_id(content_hash)
        assert cached_file_id == "PENDING"

    async def test_finalize_cache_entries(self, temp_cache, test_file, mock_client):
        """Test cache finalization after successful association."""
        vector_store = OpenAIVectorStore(mock_client, "vs-test", "test-store")
        content_hash = compute_content_hash(test_file.content)

        # Simulate a PENDING entry
        temp_cache.atomic_cache_or_get(content_hash)
        assert temp_cache.get_file_id(content_hash) == "PENDING"

        # Simulate successful upload data
        newly_uploaded = [(content_hash, "file-xyz789")]

        # Test cache finalization
        await vector_store._finalize_cache_entries(newly_uploaded, temp_cache)

        # Cache should now be finalized
        cached_file_id = temp_cache.get_file_id(content_hash)
        assert cached_file_id == "file-xyz789"

    async def test_rollback_failed_uploads(self, temp_cache, test_file, mock_client):
        """Test rollback functionality when association fails."""
        vector_store = OpenAIVectorStore(mock_client, "vs-test", "test-store")
        content_hash = compute_content_hash(test_file.content)

        # Simulate a PENDING entry
        temp_cache.atomic_cache_or_get(content_hash)
        assert temp_cache.get_file_id(content_hash) == "PENDING"

        # Simulate upload data that needs rollback
        newly_uploaded = [(content_hash, "file-rollback123")]

        # Test rollback
        await vector_store._rollback_failed_uploads(newly_uploaded, temp_cache)

        # Cache should be cleaned up
        cached_file_id = temp_cache.get_file_id(content_hash)
        assert cached_file_id is None

        # File deletion should have been called
        mock_client.files.delete.assert_called_once_with("file-rollback123")


class TestCachePollutionScenarios:
    """Test specific cache pollution scenarios."""

    async def test_association_failure_prevents_cache_pollution(
        self, temp_cache, test_file, mock_client
    ):
        """Test that association failure doesn't pollute the cache."""
        # Mock association failure
        mock_client.vector_stores.file_batches.create_and_poll = AsyncMock(
            side_effect=Exception("Association failed")
        )

        vector_store = OpenAIVectorStore(mock_client, "vs-test", "test-store")
        content_hash = compute_content_hash(test_file.content)

        # Reserve cache entry
        temp_cache.atomic_cache_or_get(content_hash)
        assert temp_cache.get_file_id(content_hash) == "PENDING"

        # Simulate the transactional flow that would happen in add_files
        newly_uploaded = await vector_store._upload_files_transactional(
            [test_file], temp_cache
        )
        assert len(newly_uploaded) == 1

        # Cache should still be PENDING after upload
        assert temp_cache.get_file_id(content_hash) == "PENDING"

        # Simulate association failure triggering rollback
        with pytest.raises(Exception, match="Association failed"):
            await mock_client.vector_stores.file_batches.create_and_poll(
                vector_store_id=vector_store.id, file_ids=[newly_uploaded[0][1]]
            )

        # Rollback should clean up cache and orphaned file
        await vector_store._rollback_failed_uploads(newly_uploaded, temp_cache)

        # Verify cache is cleaned up
        cached_file_id = temp_cache.get_file_id(content_hash)
        assert cached_file_id is None

        # Verify orphaned file was deleted
        mock_client.files.delete.assert_called_once_with("file-abc123")

    async def test_successful_flow_finalizes_cache(
        self, temp_cache, test_file, mock_client
    ):
        """Test that successful association finalizes cache correctly."""
        vector_store = OpenAIVectorStore(mock_client, "vs-test", "test-store")
        content_hash = compute_content_hash(test_file.content)

        # Reserve cache entry
        temp_cache.atomic_cache_or_get(content_hash)

        # Simulate successful transactional flow
        newly_uploaded = await vector_store._upload_files_transactional(
            [test_file], temp_cache
        )

        # Simulate successful association (no exception)
        await mock_client.vector_stores.file_batches.create_and_poll(
            vector_store_id=vector_store.id, file_ids=[newly_uploaded[0][1]]
        )

        # Finalize cache after successful association
        await vector_store._finalize_cache_entries(newly_uploaded, temp_cache)

        # Verify cache is properly finalized
        cached_file_id = temp_cache.get_file_id(content_hash)
        assert cached_file_id == "file-abc123"

        # No file deletion should occur
        mock_client.files.delete.assert_not_called()

    async def test_retry_after_rollback_works(self, temp_cache, test_file, mock_client):
        """Test that retry works correctly after rollback."""
        vector_store = OpenAIVectorStore(mock_client, "vs-test", "test-store")
        content_hash = compute_content_hash(test_file.content)

        # First attempt: Reserve and fail
        temp_cache.atomic_cache_or_get(content_hash)
        newly_uploaded = await vector_store._upload_files_transactional(
            [test_file], temp_cache
        )
        await vector_store._rollback_failed_uploads(newly_uploaded, temp_cache)

        # Verify cleanup
        assert temp_cache.get_file_id(content_hash) is None

        # Second attempt: Should be able to reserve again
        file_id, we_are_uploader = temp_cache.atomic_cache_or_get(content_hash)
        assert we_are_uploader is True
        assert file_id is None

        # Should be able to upload and finalize successfully
        newly_uploaded_2 = await vector_store._upload_files_transactional(
            [test_file], temp_cache
        )
        await vector_store._finalize_cache_entries(newly_uploaded_2, temp_cache)

        # Cache should be properly finalized
        cached_file_id = temp_cache.get_file_id(content_hash)
        assert cached_file_id == "file-abc123"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
