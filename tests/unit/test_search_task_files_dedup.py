"""Test deduplication functionality for search task files."""

import pytest
from unittest.mock import Mock, patch
from typing import List, Dict, Any

from mcp_second_brain.tools.search_task_files import SearchTaskFilesAdapter


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
    from unittest.mock import AsyncMock

    client = Mock()
    client.vector_stores = Mock()
    client.vector_stores.search = AsyncMock()
    return client


@pytest.fixture
def search_adapter(mock_openai_client):
    """Create SearchTaskFilesAdapter with mocks."""

    async def mock_get_client():
        return mock_openai_client

    with patch(
        "mcp_second_brain.tools.search_task_files.OpenAIClientFactory.get_instance"
    ) as mock_factory:
        mock_factory.return_value = mock_openai_client
        adapter = SearchTaskFilesAdapter()
        # Override the _get_client method to return our mock directly
        adapter._get_client = mock_get_client
        return adapter


class TestSearchTaskFilesDeduplication:
    """Test deduplication functionality for task files."""

    @pytest.mark.asyncio
    async def test_single_search_no_deduplication(
        self, search_adapter, mock_openai_client
    ):
        """First search should return all results without deduplication."""
        # Clear any existing dedup cache
        await search_adapter.clear_deduplication_cache()

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
        response = await search_adapter.generate(
            "test query", max_results=20, vector_store_ids=["vs_test"]
        )

        # Should see all 3 results
        assert "Found 3 results" in response
        assert "Content: Content 1" in response
        assert "Content: Content 2" in response
        assert "Content: Content 3" in response

    @pytest.mark.asyncio
    async def test_duplicate_results_filtered_across_searches(
        self, search_adapter, mock_openai_client
    ):
        """Duplicate results should be filtered across multiple searches."""
        # Clear any existing dedup cache
        await search_adapter.clear_deduplication_cache()

        # First search
        results1 = [
            MockSearchResult("Document A", 0.9, file_id="doc1"),
            MockSearchResult("Document B", 0.8, file_id="doc2"),
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results1
        )

        response1 = await search_adapter.generate(
            "query 1", max_results=20, vector_store_ids=["vs_test1"]
        )
        assert "Found 2 results" in response1

        # Second search with overlapping results
        results2 = [
            MockSearchResult("Document B", 0.85, file_id="doc2"),  # Duplicate
            MockSearchResult("Document C", 0.75, file_id="doc3"),  # New
            MockSearchResult("Document A", 0.7, file_id="doc1"),  # Duplicate
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results2
        )

        response2 = await search_adapter.generate(
            "query 2", max_results=20, vector_store_ids=["vs_test2"]
        )

        # Should only see the new result
        assert "Found 1 result" in response2
        assert "Content: Document C" in response2
        assert "Content: Document A" not in response2
        assert "Content: Document B" not in response2

    @pytest.mark.asyncio
    async def test_task_files_deduplication_independent_from_memory(
        self, search_adapter, tmp_path
    ):
        """Task files deduplication should be independent from memory deduplication."""
        from mcp_second_brain.tools.search_history import SearchHistoryAdapter

        # Clear task files cache
        await search_adapter.clear_deduplication_cache()

        # Create memory adapter with mocked dependencies
        mock_settings = Mock()
        mock_settings.openai_api_key = "test-key"

        with patch(
            "mcp_second_brain.tools.search_history.get_settings",
            return_value=mock_settings,
        ):
            with patch("mcp_second_brain.tools.search_history.get_memory_config"):
                # Patch OpenAI client creation
                with patch(
                    "mcp_second_brain.tools.search_history.OpenAI", return_value=Mock()
                ):
                    # Create test database path
                    test_db_path = (
                        tmp_path / ".cache" / "mcp-second-brain" / "session_cache.db"
                    )
                    test_db_path.parent.mkdir(parents=True, exist_ok=True)

                    history_adapter = SearchHistoryAdapter()
                    # Force reinitialize deduplicator with test path
                    from mcp_second_brain.tools.search_dedup_sqlite import (
                        SQLiteSearchDeduplicator,
                    )
                    from mcp_second_brain.tools.search_history import (
                        SearchHistoryAdapter as SHA,
                    )

                    SHA._deduplicator = SQLiteSearchDeduplicator(
                        db_path=test_db_path, ttl_hours=24
                    )
                    await history_adapter.clear_deduplication_cache("default")

                # Verify they use different deduplicators
                # Task files uses in-memory deduplicator with cache_name
                assert hasattr(search_adapter._deduplicator, "cache_name")
                assert search_adapter._deduplicator.cache_name == "task_files"
                # History uses SQLite deduplicator without cache_name
                assert not hasattr(history_adapter._deduplicator, "cache_name")
                # They should have different deduplicator types
                assert (
                    type(search_adapter._deduplicator).__name__
                    != type(history_adapter._deduplicator).__name__
                )

    @pytest.mark.asyncio
    async def test_deduplication_with_metadata(
        self, search_adapter, mock_openai_client
    ):
        """Deduplication should work with metadata-rich results."""
        # Clear any existing dedup cache
        await search_adapter.clear_deduplication_cache()

        # Results with metadata
        results = [
            MockSearchResult(
                "API Documentation",
                0.9,
                file_id="api_doc",
                metadata={"filename": "api.md", "section": "authentication"},
            ),
            MockSearchResult(
                "API Documentation",  # Same content, same file
                0.8,
                file_id="api_doc",
                metadata={"filename": "api.md", "section": "authorization"},
            ),
        ]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results
        )

        response = await search_adapter.generate(
            "API docs", max_results=20, vector_store_ids=["vs_docs"]
        )

        # Should only see one result (first one with higher score)
        assert "Found 1 result" in response
        assert "File: api.md" in response

    @pytest.mark.asyncio
    async def test_cache_clearing_works(self, search_adapter, mock_openai_client):
        """Cache clearing should allow previously seen content to appear again."""
        # First search
        results = [MockSearchResult("Content X", 0.9, file_id="fileX")]
        mock_openai_client.vector_stores.search.return_value = MockSearchResponse(
            results
        )

        await search_adapter.generate(
            "query 1", max_results=20, vector_store_ids=["vs_1"]
        )

        # Clear cache
        await search_adapter.clear_deduplication_cache()

        # Same search should return the result again
        response = await search_adapter.generate(
            "query 2", max_results=20, vector_store_ids=["vs_2"]
        )
        assert "Found 1 result" in response
        assert "Content: Content X" in response
