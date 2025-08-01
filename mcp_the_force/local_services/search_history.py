"""Search history service for searching project history stores."""

from typing import List, Dict, Any, Optional
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from ..memory.async_config import get_async_memory_config
from ..vectorstores.manager import VectorStoreManager
from ..utils.redaction import redact_secrets
from ..tools.search_dedup_sqlite import SQLiteSearchDeduplicator
from ..utils.scope_manager import scope_manager

logger = logging.getLogger(__name__)

# Semaphore to limit concurrent searches
search_semaphore = asyncio.Semaphore(5)


def _calculate_relative_time(timestamp: int) -> str:
    """Calculate human-readable relative time from timestamp."""
    now = datetime.now(timezone.utc)
    then = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    delta = now - then

    # Calculate relative time
    if delta.days > 365:
        years = delta.days // 365
        return f"{years} year{'s' if years != 1 else ''} ago"
    elif delta.days > 30:
        months = delta.days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    elif delta.days > 0:
        return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
    elif delta.seconds > 3600:
        hours = delta.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif delta.seconds > 60:
        minutes = delta.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "just now"


class SearchHistoryService:
    """Local service for searching project history stores."""

    # Class-level singletons
    _vector_store_manager: Optional[VectorStoreManager] = None
    _memory_config: Optional[Any] = None  # AsyncMemoryConfig
    _deduplicator = None
    _deduplicator_lock = asyncio.Lock()
    _init_lock = asyncio.Lock()

    def __init__(
        self,
        vector_store_manager: Optional[VectorStoreManager] = None,
        memory_config: Optional[Any] = None,
        deduplicator: Optional[Any] = None,
    ):
        self.vector_store_manager = vector_store_manager
        self.memory_config = memory_config

        # Use provided dependencies if given (for tests)
        if vector_store_manager and memory_config:
            self._deduplicator = deduplicator
            return

        # Otherwise, initialize singletons once
        if SearchHistoryService._vector_store_manager is None:
            SearchHistoryService._vector_store_manager = VectorStoreManager()
        if SearchHistoryService._memory_config is None:
            SearchHistoryService._memory_config = get_async_memory_config()

        self.vector_store_manager = SearchHistoryService._vector_store_manager
        self.memory_config = SearchHistoryService._memory_config
        self._ensure_deduplicator()

    def _ensure_deduplicator(self):
        """Ensure the SQLite deduplicator is initialized."""
        if SearchHistoryService._deduplicator is None:
            # Use the main session DB path from settings for consistency
            from ..config import get_settings

            settings = get_settings()
            db_path = Path(settings.session.db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

            SearchHistoryService._deduplicator = SQLiteSearchDeduplicator(
                db_path=db_path,
                ttl_hours=24,  # 24 hour TTL for search deduplication
            )
            logger.info(
                f"[SEARCH_HISTORY] Initialized SQLite deduplicator at project-local path {db_path}"
            )

    async def clear_deduplication_cache(self, session_id: Optional[str] = None):
        """Clear the deduplication cache.

        Args:
            session_id: If provided, only clear cache for this session.
                       If None, this is a no-op (we don't clear all sessions).
        """
        if session_id and SearchHistoryService._deduplicator:
            await SearchHistoryService._deduplicator.clear_session(session_id)
            logger.info(
                f"[SEARCH_HISTORY] Cleared deduplication cache for session {session_id}"
            )

    def _redact_content(self, content: str) -> str:
        """Redact sensitive information from content."""
        # Get project root from scope manager
        project_root = getattr(scope_manager, "project_root", None)
        if project_root:
            content = redact_secrets(content)
        return content

    async def execute(self, **kwargs: Any) -> str:
        """Execute search with parameters matching the tool interface."""
        query = kwargs.get("query", "")
        max_results = int(kwargs.get("max_results", 40))
        store_types = kwargs.get("store_types", None)
        session_id = kwargs.get("session_id", None)

        # Convert single query to list for the search method
        queries = [query] if query else []

        # Call the search method
        result = await self.search(
            queries=queries,
            max_results=max_results,
            store_types=store_types,
            session_id=session_id,
        )

        # Format results as a string
        return self._format_results(result)

    def _format_results(self, result: Dict[str, Any]) -> str:
        """Format search results for display."""
        formatted = []

        results = result.get("results", [])
        # metadata = result.get("metadata", {})

        # DEBUG: Log what we're formatting
        logger.info(f"[SEARCH_HISTORY_DEBUG] Formatting {len(results)} results for display")

        if not results:
            return "No results found in project history."

        formatted.append(f"Found {len(results)} results in project history:\n")

        for idx, item in enumerate(results, 1):
            formatted.append(f"\n--- Result {idx} ---")
            formatted.append(f"Type: {item.get('store_type', 'unknown')}")
            relative_time = item.get("metadata", {}).get("relative_time", "unknown")
            formatted.append(f"Time: {relative_time}")
            if item.get("metadata", {}).get("author"):
                formatted.append(f"Author: {item['metadata']['author']}")
            formatted.append(f"\nContent:\n{item.get('content', '')}")
            formatted.append("-" * 40)

        return "\n".join(formatted)

    async def search(
        self,
        queries: List[str],
        max_results: int = 40,
        store_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search across all configured vector stores.

        Args:
            queries: List of search queries
            max_results: Maximum number of results to return
            store_types: Types of stores to search (conversation, commit, etc.)
            session_id: Optional session ID for deduplication

        Returns:
            Dictionary with search results organized by store
        """
        # Ensure max_results is an integer
        max_results = int(max_results)

        if store_types is None:
            store_types = ["conversation", "commit"]

        logger.info(
            f"[SEARCH_HISTORY] Searching {len(queries)} queries across {store_types} stores"
        )

        stores_to_search = []

        # Determine which stores to search
        for store_type in store_types:
            if store_type == "conversation":
                if self.memory_config:
                    store_id = await self.memory_config.get_active_conversation_store()
                    if store_id:
                        stores_to_search.append(("conversation", store_id))
            elif store_type == "commit":
                if self.memory_config:
                    store_id = await self.memory_config.get_active_commit_store()
                    if store_id:
                        stores_to_search.append(("commit", store_id))
            # Add more store types as needed

        if not stores_to_search:
            logger.warning(
                f"[SEARCH_HISTORY] No valid stores found for types: {store_types}"
            )
            return {
                "results": [],
                "metadata": {"total_results": 0, "stores_searched": 0},
            }

        # Search each store concurrently
        async with search_semaphore:
            tasks = []
            for store_type, store_id in stores_to_search:
                for query in queries:
                    task = self._search_single_store(
                        store_type, store_id, query, max_results
                    )
                    tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        seen_contents = set()
        formatted_results = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Search task {i} failed: {result}")
                continue

            store_type = stores_to_search[i // len(queries)][0]
            if not isinstance(result, Exception):
                logger.debug(
                    f"Processing result type: {type(result)}, length: {len(result) if hasattr(result, '__len__') else 'N/A'}"
                )
                if isinstance(result, list):
                    for item in result:
                        # Deduplicate by content
                        content = str(item.get("content", ""))
                        content_key = content[:200]  # Use first 200 chars as key
                        if content_key in seen_contents:
                            continue
                        seen_contents.add(content_key)

                        # Redact sensitive information
                        item["content"] = self._redact_content(
                            str(item.get("content", ""))
                        )

                        # Add relative time if timestamp is available
                        if "metadata" in item and isinstance(item["metadata"], dict):
                            timestamp = item["metadata"].get("timestamp")
                            if timestamp:
                                item["metadata"]["relative_time"] = (
                                    _calculate_relative_time(timestamp)
                                )

                        formatted_results.append(
                            {
                                "content": item["content"],
                                "store_type": store_type,
                                "store_id": item["store_id"],
                                "score": item.get("score", 0),
                                "metadata": item.get("metadata", {}),
                            }
                        )

        # Sort by score
        formatted_results.sort(key=lambda x: x["score"], reverse=True)
        
        # DEBUG: Log results before deduplication
        logger.info(f"[SEARCH_HISTORY_DEBUG] Before deduplication: {len(formatted_results)} results")
        for i, result in enumerate(formatted_results[:3]):  # Show first 3 results
            logger.info(f"[SEARCH_HISTORY_DEBUG] Result {i}: {result.get('content', '')[:100]}...")

        # Apply session-based deduplication if session_id is provided
        if session_id and SearchHistoryService._deduplicator:
            # Call deduplicate_results with proper parameters
            deduplicated, duplicate_count = (
                SearchHistoryService._deduplicator.deduplicate_results(
                    all_results=formatted_results,
                    max_results=max_results,
                    session_id=session_id,
                    query=" AND ".join(queries) if queries else "",
                )
            )
            formatted_results = deduplicated
            if duplicate_count > 0:
                logger.info(
                    f"[SEARCH_HISTORY] Deduplicated {duplicate_count} results for session {session_id}"
                )

        # Limit total results
        formatted_results = formatted_results[:max_results]

        # DEBUG: Log final results being returned
        logger.info(f"[SEARCH_HISTORY_DEBUG] After deduplication: {len(formatted_results)} results")
        for i, result in enumerate(formatted_results[:3]):  # Show first 3 results
            logger.info(f"[SEARCH_HISTORY_DEBUG] Final result {i}: {result.get('content', '')[:100]}...")

        return {
            "results": formatted_results,
            "metadata": {
                "total_results": len(formatted_results),
                "stores_searched": len(stores_to_search),
                "queries": queries,
                "store_types": store_types,
            },
        }

    def _get_content_hash(self, result: Dict[str, Any]) -> str:
        """Get a hash key for deduplication."""
        # Use first 500 chars of content as the deduplication key
        # This allows similar but not identical content to be deduplicated
        content = str(result.get("content", ""))
        return content[:500]

    async def _search_single_store(
        self, store_type: str, store_id: str, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Search a single vector store."""
        try:
            logger.debug(
                f"[SEARCH_HISTORY] Searching store {store_id} ({store_type}) for: '{query}'"
            )

            # Get the store using vector store manager
            if not self.vector_store_manager:
                logger.error("Vector store manager not initialized")
                return []

            # Get store info from cache to determine provider
            store_info = await self.vector_store_manager.vector_store_cache.get_store(
                vector_store_id=store_id
            )

            if not store_info:
                logger.error(f"Store {store_id} not found in cache")
                return []

            provider = store_info["provider"]
            client = self.vector_store_manager._get_client(provider)

            # Get the store instance
            store = await client.get(store_id)

            # Search using the vector store protocol
            search_results = await store.search(query=query, k=max_results)

            results = []
            for item in search_results:
                result = {
                    "content": item.content,
                    "store_id": store_id,
                    "score": item.score,
                }

                # Add file_id if available
                if hasattr(item, "file_id"):
                    result["file_id"] = item.file_id

                # Add metadata if available
                if item.metadata:
                    result["metadata"] = item.metadata

                results.append(result)

            logger.debug(
                f"[SEARCH_HISTORY] Store {store_id} returned {len(results)} results for query '{query}'"
            )
            return results

        except Exception as e:
            logger.error(f"Failed to search store {store_id}: {e}")
            raise
