"""Search project memory tool implementation.

This provides a unified way for all models (OpenAI and Gemini) to search
across project memory stores without the 2-store limitation.
"""

from typing import List, Dict, Any, TYPE_CHECKING, Set
import logging
import asyncio
import hashlib
from ..utils.thread_pool import get_shared_executor

from openai import OpenAI
import fastmcp.exceptions

if TYPE_CHECKING:
    pass

from ..memory.config import get_memory_config
from ..utils.redaction import redact_secrets
from ..config import get_settings
from ..adapters.base import BaseAdapter
from .base import ToolSpec
from .descriptors import Route
from .registry import tool

logger = logging.getLogger(__name__)

# Thread pool for synchronous OpenAI operations (shared)
executor = get_shared_executor()

# Semaphore to limit concurrent searches
search_semaphore = asyncio.Semaphore(5)


@tool
class SearchProjectMemory(ToolSpec):
    """Search across all project memory stores."""

    model_name = "memory_search"
    adapter_class = "SearchMemoryAdapter"
    context_window = 0  # Not applicable for search
    timeout = 30  # 30 second timeout for searches

    # Parameters
    query = Route.prompt(description="Search query or semicolon-separated queries")
    max_results = Route.prompt(
        description="Maximum results to return (default: 20)",
        default=20,
    )
    store_types = Route.prompt(
        description="Types of stores to search (default: ['conversation', 'commit'])",
        default_factory=lambda: ["conversation", "commit"],
    )


class SearchMemoryAdapter(BaseAdapter):
    """Adapter for searching project memory stores."""

    model_name = "memory_search"
    context_window = 0  # Not applicable
    description_snippet = "Search project memory stores"

    # Class-level deduplication cache shared across instances
    _dedup_cache: Set[str] = set()
    _dedup_lock = asyncio.Lock()

    def __init__(self, model_name: str = "memory_search"):
        self.model_name = model_name
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.memory_config = get_memory_config()

    @staticmethod
    def _compute_content_hash(content: str, file_id: str = "") -> str:
        """Compute a hash for deduplication based on content and file_id."""
        # Include both content and file_id to handle same content from different files
        combined = f"{content}:{file_id}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    async def clear_deduplication_cache(self):
        """Clear the deduplication cache."""
        async with self._dedup_lock:
            self._dedup_cache.clear()
        logger.info("Cleared deduplication cache")

    async def generate(
        self,
        prompt: str,
        vector_store_ids: List[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Search memory stores and return formatted results.

        This method is called by the ToolExecutor when any model
        (OpenAI or Gemini) invokes the search_project_memory function.
        """
        # Extract search parameters
        query = kwargs.get("query", prompt)
        max_results = kwargs.get("max_results", 20)
        store_types = kwargs.get("store_types", ["conversation", "commit"])
        include_duplicates_metadata = kwargs.get("include_duplicates_metadata", False)

        if not query:
            raise fastmcp.exceptions.ToolError("Search query is required")

        try:
            # Get memory store IDs filtered by type
            stores_to_search = self.memory_config.get_store_ids_by_type(store_types)

            if not stores_to_search:
                return f"No {', '.join(store_types)} stores found"

            # Support multiple queries (semicolon-separated)
            queries = (
                [q.strip() for q in query.split(";") if q.strip()]
                if ";" in query
                else [query]
            )

            # Search all stores in parallel
            search_tasks = []
            for store_id in stores_to_search:
                for q in queries:
                    # Ensure each query gets at least 1 result slot
                    per_query_limit = max(1, max_results // max(len(queries), 1))
                    task = self._search_single_store(q, store_id, per_query_limit)
                    search_tasks.append(task)

            # Wait for all searches with timeout
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*search_tasks, return_exceptions=True),
                    timeout=10.0,  # 10 second timeout for all searches
                )
            except asyncio.TimeoutError:
                logger.warning("Memory search timed out")
                raise fastmcp.exceptions.ToolError(
                    "Memory search timed out after 10 seconds"
                )

            # Aggregate and sort results
            all_results = []
            errors = 0

            for result in results:
                if isinstance(result, Exception):
                    errors += 1
                    logger.warning(f"Search error: {result}")
                elif isinstance(result, list):
                    all_results.extend(result)

            # Sort by relevance score
            all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

            # Apply deduplication
            deduplicated_results = []
            duplicate_count = 0

            async with self._dedup_lock:
                for search_result in all_results:
                    # Compute hash for this result
                    content = search_result.get("content", "")
                    # Try to extract file_id from the result
                    file_id = ""
                    if "file_id" in search_result:
                        file_id = search_result["file_id"]
                    elif "metadata" in search_result and "file_id" in search_result.get(
                        "metadata", {}
                    ):
                        file_id = search_result["metadata"]["file_id"]

                    content_hash = self._compute_content_hash(content, file_id)

                    # Check if we've seen this content before
                    if content_hash not in self._dedup_cache:
                        self._dedup_cache.add(content_hash)
                        deduplicated_results.append(search_result)

                        # Stop when we have enough results
                        if len(deduplicated_results) >= max_results:
                            break
                    else:
                        duplicate_count += 1

            # Format response
            if not deduplicated_results:
                return f"No results found for query: '{query}'"

            # Build formatted response with metadata
            response_parts = [
                f"Found {len(deduplicated_results)} results across {len(stores_to_search)} memory stores:"
            ]

            if include_duplicates_metadata and duplicate_count > 0:
                response_parts[0] += (
                    f" ({duplicate_count} duplicate result{'s' if duplicate_count != 1 else ''} filtered)"
                )

            for i, search_result in enumerate(deduplicated_results, 1):
                response_parts.append(f"\n--- Result {i} ---")

                # Add metadata
                metadata = search_result.get("metadata", {})
                if metadata.get("type"):
                    response_parts.append(f"Type: {metadata['type']}")
                if metadata.get("datetime"):
                    response_parts.append(f"Date: {metadata['datetime']}")
                if metadata.get("session_id"):
                    response_parts.append(f"Session: {metadata['session_id']}")
                if metadata.get("branch"):
                    response_parts.append(f"Branch: {metadata['branch']}")

                response_parts.append(f"Score: {search_result.get('score', 'N/A')}")

                # Add content (redacted)
                content = redact_secrets(search_result.get("content", ""))
                # Truncate very long content
                if len(content) > 500:
                    content = content[:500] + "..."
                response_parts.append(f"Content: {content}")

            if errors > 0:
                response_parts.append(f"\nNote: {errors} searches failed")

            return "\n".join(response_parts)

        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            raise fastmcp.exceptions.ToolError(f"Error searching memory: {e}")

    async def _search_single_store(
        self, query: str, store_id: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Search a single vector store."""
        async with search_semaphore:  # Limit concurrent searches
            try:
                # OpenAI search is synchronous, run in thread pool
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    executor,
                    lambda: self.client.vector_stores.search(
                        vector_store_id=store_id,
                        query=query,
                        max_num_results=max_results,
                    ),
                )

                # Format results
                results = []
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

                return results

            except Exception as e:
                logger.error(f"Failed to search store {store_id}: {e}")
                raise
