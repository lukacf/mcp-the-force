"""Search history service for searching project history stores."""

from typing import List, Dict, Any, Optional
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from ..memory.config import get_memory_config
from ..utils.redaction import redact_secrets
from ..utils.thread_pool import get_shared_executor
from ..config import get_settings
from ..tools.search_dedup_sqlite import SQLiteSearchDeduplicator
from ..utils.scope_manager import scope_manager

logger = logging.getLogger(__name__)

# Thread pool for synchronous OpenAI operations (shared)
executor = get_shared_executor()

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

    # Class-level SQLite deduplicator (singleton)
    _deduplicator = None
    _deduplicator_lock = asyncio.Lock()

    def __init__(self):
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.memory_config = get_memory_config()
        self._ensure_deduplicator()

    def _ensure_deduplicator(self):
        """Ensure the SQLite deduplicator is initialized."""
        if SearchHistoryService._deduplicator is None:
            # Use the same database as memory config
            home = Path.home()
            cache_dir = home / ".cache" / "mcp-the-force"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = cache_dir / "session_cache.db"

            SearchHistoryService._deduplicator = SQLiteSearchDeduplicator(
                db_path=db_path,
                ttl_hours=24,  # 24 hour TTL for search deduplication
            )
            logger.info(
                f"[SEARCH_HISTORY] Initialized SQLite deduplicator at {db_path}"
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

        # Convert single query to list for the search method
        queries = [query] if query else []

        # Call the search method
        result = await self.search(
            queries=queries, max_results=max_results, store_types=store_types
        )

        # Format results as a string
        return self._format_results(result)

    def _format_results(self, result: Dict[str, Any]) -> str:
        """Format search results for display."""
        formatted = []

        results = result.get("results", [])
        # metadata = result.get("metadata", {})

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
                store_id = self.memory_config.get_active_conversation_store()
                if store_id:
                    stores_to_search.append(("conversation", store_id))
            elif store_type == "commit":
                store_id = self.memory_config.get_active_commit_store()
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
                for item in result:
                    # Deduplicate by content
                    content = str(item.get("content", ""))
                    content_key = content[:200]  # Use first 200 chars as key
                    if content_key in seen_contents:
                        continue
                    seen_contents.add(content_key)

                    # Redact sensitive information
                    item["content"] = self._redact_content(str(item.get("content", "")))

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

        # Apply session-based deduplication if session_id is provided
        if session_id and SearchHistoryService._deduplicator:
            original_count = len(formatted_results)
            formatted_results = await SearchHistoryService._deduplicator.filter_results(
                session_id, formatted_results, self._get_content_hash
            )
            dedup_count = original_count - len(formatted_results)
            if dedup_count > 0:
                logger.info(
                    f"[SEARCH_HISTORY] Deduplicated {dedup_count} results for session {session_id}"
                )

        # Limit total results
        formatted_results = formatted_results[:max_results]

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

            # Run synchronous OpenAI call in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                executor,
                lambda: self.client.vector_stores.search(
                    vector_store_id=store_id,
                    query=query,
                    max_num_results=max_results,
                ),
            )

            results = []
            if response and hasattr(response, "data"):
                for item in response.data:
                    # Extract content - handle different response formats
                    content = ""
                    if hasattr(item, "content"):
                        if isinstance(item.content, str):
                            content = item.content
                        elif isinstance(item.content, list) and item.content:
                            # Try to extract text from first content item
                            first_item = item.content[0]
                            if hasattr(first_item, "text"):
                                if hasattr(first_item.text, "value"):
                                    content = first_item.text.value
                                else:
                                    content = str(first_item.text)

                    result = {
                        "content": content,
                        "store_id": store_id,
                        "score": getattr(item, "score", 0),
                    }

                    # Add file_id if available
                    if hasattr(item, "file_id") and item.file_id:
                        result["file_id"] = item.file_id

                    # Add metadata if available
                    if hasattr(item, "metadata") and item.metadata:
                        result["metadata"] = item.metadata

                    results.append(result)

            logger.debug(
                f"[SEARCH_HISTORY] Store {store_id} returned {len(results)} results for query '{query}'"
            )
            return results

        except Exception as e:
            logger.error(f"Failed to search store {store_id}: {e}")
            raise
