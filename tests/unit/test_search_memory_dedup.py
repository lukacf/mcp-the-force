"""Test deduplication functionality for search memory."""

import pytest
from unittest.mock import Mock, patch
from typing import List, Dict, Any

from mcp_second_brain.tools.search_history import SearchHistoryAdapter


class MockSearchResult:
    """Mock OpenAI search result."""

    def __init__(
        self,
        content: str,
        score: float = 0.9,
        metadata: Dict[str, Any] = None,
        file_id: str = None,
    ):
        self.content = [Mock(text=Mock(value=content))]
        self.score = score
        self.metadata = metadata or {}
        self.file_id = file_id or f"file_{hash(content) % 1000}"


class MockSearchResponse:
    """Mock OpenAI search response."""

    def __init__(self, results: List[MockSearchResult]):
        self.data = results


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    client = Mock()
    client.vector_stores = Mock()
    return client


@pytest.fixture
def mock_memory_config():
    """Mock memory config."""
    config = Mock()
    config.get_store_ids_by_type = Mock(return_value=["store1", "store2"])
    return config


@pytest.fixture
def search_adapter(mock_openai_client, mock_memory_config, tmp_path):
    """Create SearchHistoryAdapter with mocks."""
    mock_settings = Mock()
    mock_settings.openai_api_key = "test-key"

    with patch(
        "mcp_second_brain.tools.search_history.get_settings", return_value=mock_settings
    ):
        with patch(
            "mcp_second_brain.tools.search_history.get_memory_config",
            return_value=mock_memory_config,
        ):
            # Patch OpenAI client creation
            with patch(
                "mcp_second_brain.tools.search_history.OpenAI",
                return_value=mock_openai_client,
            ):
                # Create test database path
                test_db_path = (
                    tmp_path / ".cache" / "mcp-second-brain" / "session_cache.db"
                )
                test_db_path.parent.mkdir(parents=True, exist_ok=True)

                # Initialize adapter with test database
                adapter = SearchHistoryAdapter()
                # Force reinitialize deduplicator with test path
                from mcp_second_brain.tools.search_dedup_sqlite import (
                    SQLiteSearchDeduplicator,
                )

                SearchHistoryAdapter._deduplicator = SQLiteSearchDeduplicator(
                    db_path=test_db_path, ttl_hours=24
                )
                return adapter


class TestSearchHistoryDeduplication:
    """Test deduplication functionality."""

    @pytest.mark.asyncio
    async def test_single_search_no_deduplication(
        self, search_adapter, mock_openai_client
    ):
        """First search should return all results without deduplication."""
        # Clear any existing dedup cache for the default session
        await search_adapter.clear_deduplication_cache("default")

        # Setup mock results
        results = [
            MockSearchResult("Content 1", 0.9, file_id="file1"),
            MockSearchResult("Content 2", 0.8, file_id="file2"),
            MockSearchResult("Content 3", 0.7, file_id="file3"),
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results
        )

        # Perform search
        response = await search_adapter.generate("test query", max_results=20)

        # Should see all 3 results
        assert "Found 3 results" in response
        assert "Content: Content 1" in response
        assert "Content: Content 2" in response
        assert "Content: Content 3" in response

    @pytest.mark.asyncio
    async def test_duplicate_results_filtered(self, search_adapter, mock_openai_client):
        """Duplicate results should be filtered out in subsequent searches."""
        # Clear any existing dedup cache for the default session
        await search_adapter.clear_deduplication_cache("default")

        # First search
        results1 = [
            MockSearchResult("Content 1", 0.9, file_id="file1"),
            MockSearchResult("Content 2", 0.8, file_id="file2"),
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results1
        )

        response1 = await search_adapter.generate("query 1", max_results=20)
        assert "Found 2 results" in response1

        # Second search with overlapping results
        results2 = [
            MockSearchResult("Content 2", 0.85, file_id="file2"),  # Duplicate
            MockSearchResult("Content 3", 0.75, file_id="file3"),  # New
            MockSearchResult("Content 1", 0.7, file_id="file1"),  # Duplicate
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results2
        )

        response2 = await search_adapter.generate("query 2", max_results=20)

        # Should only see the new result
        assert "Found 1 result" in response2
        assert "Content: Content 3" in response2
        assert "Content: Content 1" not in response2
        assert "Content: Content 2" not in response2

    @pytest.mark.asyncio
    async def test_deduplication_tracks_by_content_hash(
        self, search_adapter, mock_openai_client
    ):
        """Deduplication should track by content hash, not just file_id."""
        # Clear any existing dedup cache for the default session
        await search_adapter.clear_deduplication_cache("default")

        # First search
        results1 = [
            MockSearchResult("Chunk 1 from file", 0.9, file_id="file1"),
            MockSearchResult(
                "Chunk 2 from file", 0.8, file_id="file1"
            ),  # Same file, different chunk
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results1
        )

        response1 = await search_adapter.generate("query 1", max_results=20)
        assert "Found 2 results" in response1

        # Second search
        results2 = [
            MockSearchResult(
                "Chunk 1 from file", 0.85, file_id="file1"
            ),  # Duplicate chunk
            MockSearchResult(
                "Chunk 3 from file", 0.7, file_id="file1"
            ),  # New chunk from same file
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results2
        )

        response2 = await search_adapter.generate("query 2", max_results=20)

        # Should only see the new chunk
        assert "Found 1 result" in response2
        assert "Content: Chunk 3 from file" in response2
        assert "Content: Chunk 1 from file" not in response2

    @pytest.mark.asyncio
    async def test_deduplication_preserves_metadata(
        self, search_adapter, mock_openai_client
    ):
        """Deduplication should note when content was seen before."""
        # Clear any existing dedup cache for the default session
        await search_adapter.clear_deduplication_cache("default")

        # First search
        results1 = [
            MockSearchResult(
                "Content 1", 0.9, file_id="file1", metadata={"type": "conversation"}
            ),
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results1
        )

        await search_adapter.generate("query 1", max_results=20)

        # Second search with same content
        results2 = [
            MockSearchResult(
                "Content 1", 0.95, file_id="file1", metadata={"type": "conversation"}
            ),
            MockSearchResult(
                "Content 2", 0.8, file_id="file2", metadata={"type": "commit"}
            ),
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results2
        )

        response2 = await search_adapter.generate(
            "query 2", max_results=20, include_duplicates_metadata=True
        )

        # Should see new content and metadata about duplicate
        assert "Found 1 result" in response2
        assert "Content: Content 2" in response2
        # With 2 stores returning the same results, we get 3 duplicates total:
        # - 2 instances of "Content 1" (one per store)
        # - 1 extra instance of "Content 2" (from second store)
        assert (
            "(3 duplicate results filtered)" in response2
            or "previously seen" in response2.lower()
        )

    @pytest.mark.asyncio
    async def test_max_results_reduced_to_20(self, search_adapter, mock_openai_client):
        """Default max_results should be 20, not 40."""
        # Clear any existing dedup cache for the default session
        await search_adapter.clear_deduplication_cache("default")

        # Create 25 results
        results = [
            MockSearchResult(f"Content {i}", 0.9 - i * 0.01, file_id=f"file{i}")
            for i in range(25)
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results
        )

        # Search without specifying max_results (should use default of 20)
        response = await search_adapter.generate("test query")

        # Should only see 20 results
        assert "Found 20 results" in response
        # Check that result 21 is not included
        assert "Content 20" not in response  # 0-indexed, so Content 20 is the 21st

    @pytest.mark.asyncio
    async def test_deduplication_across_multiple_stores(
        self, search_adapter, mock_openai_client
    ):
        """Deduplication should work across different memory stores."""
        # Clear any existing dedup cache for the default session
        await search_adapter.clear_deduplication_cache("default")

        # Setup to return different results per store
        call_count = 0

        def search_side_effect(*args, **kwargs):
            nonlocal call_count
            if call_count == 0:  # First store
                results = [MockSearchResult("Shared content", 0.9, file_id="file1")]
            else:  # Second store
                results = [MockSearchResult("Shared content", 0.8, file_id="file1")]
            call_count += 1
            return MockSearchResponse(results)

        mock_openai_client.vector_stores.search.side_effect = search_side_effect

        response = await search_adapter.generate("test query", max_results=20)

        # Should only see the content once (from higher scoring result)
        assert "Found 1 result" in response
        assert response.count("Content: Shared content") == 1

    @pytest.mark.asyncio
    async def test_deduplication_resets_on_clear(
        self, search_adapter, mock_openai_client
    ):
        """Deduplication cache can be cleared to start fresh."""
        # First search
        results = [MockSearchResult("Content 1", 0.9, file_id="file1")]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results
        )

        await search_adapter.generate(
            "query 1", max_results=20, session_id="test-session"
        )

        # Clear deduplication cache for the session
        await search_adapter.clear_deduplication_cache("test-session")

        # Same search in same session should now return the result again
        response = await search_adapter.generate(
            "query 2", max_results=20, session_id="test-session"
        )
        assert "Found 1 result" in response
        assert "Content: Content 1" in response
