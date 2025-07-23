"""Search project history tool implementation.

This provides a unified way for all models (OpenAI and Gemini) to search
across project history stores without the 2-store limitation.
"""

from typing import List, Dict, Any, TYPE_CHECKING
import logging
import asyncio
from datetime import datetime, timezone
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
from .search_dedup import SearchDeduplicator

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


@tool
class SearchProjectHistory(ToolSpec):
    """Search across all project history stores."""

    model_name = "history_search"
    adapter_class = "SearchHistoryAdapter"
    context_window = 0  # Not applicable for search
    timeout = 30  # 30 second timeout for searches

    # Parameters
    query = Route.prompt(description="Search query or semicolon-separated queries")
    max_results = Route.prompt(
        description="Maximum results to return (default: 40)",
        default=40,
    )
    store_types = Route.prompt(
        description="Types of stores to search (default: ['conversation', 'commit'])",
        default_factory=lambda: ["conversation", "commit"],
    )


class SearchHistoryAdapter(BaseAdapter):
    """Adapter for searching project history stores."""

    model_name = "history_search"
    context_window = 0  # Not applicable
    description_snippet = "Search project history stores"

    # Class-level deduplicator shared across instances
    _deduplicator = SearchDeduplicator("memory")

    def __init__(self, model_name: str = "history_search"):
        self.model_name = model_name
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.memory_config = get_memory_config()

    async def clear_deduplication_cache(self):
        """Clear the deduplication cache."""
        await self._deduplicator.clear_cache()

    async def generate(
        self,
        prompt: str,
        vector_store_ids: List[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Search memory stores and return formatted results.

        This method is called by the ToolExecutor when any model
        (OpenAI or Gemini) invokes the search_project_history function.
        """
        # Extract search parameters
        query = kwargs.get("query")
        if not query:
            # Heuristic: treat prompt as a query only if it's short
            # and looks like plain text (no angle-brackets XML).
            if prompt and len(prompt) <= 256 and "<" not in prompt:
                query = prompt
            else:
                query = ""
        max_results = kwargs.get("max_results", 20)
        # Ensure max_results is an integer
        if isinstance(max_results, str):
            max_results = int(max_results)
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
            (
                deduplicated_results,
                duplicate_count,
            ) = await self._deduplicator.deduplicate_results(all_results, max_results)

            # Format response
            if not deduplicated_results:
                return f"No results found for query: '{query}'"

            # Build formatted response with metadata
            response_parts = [
                f"Found {len(deduplicated_results)} results in project HISTORY (⚠️ May be outdated):"
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

                # Add relative time if timestamp is available
                if metadata.get("timestamp"):
                    relative_time = _calculate_relative_time(int(metadata["timestamp"]))
                    if metadata.get("datetime"):
                        response_parts.append(
                            f"Date: {metadata['datetime']} ({relative_time})"
                        )
                    else:
                        response_parts.append(f"Date: {relative_time}")
                elif metadata.get("datetime"):
                    response_parts.append(f"Date: {metadata['datetime']}")

                if metadata.get("session_id"):
                    response_parts.append(f"Session: {metadata['session_id']}")
                if metadata.get("branch"):
                    branch_info = f"Branch: {metadata['branch']}"
                    # Add commits behind info if available
                    if metadata.get("commits_since_main"):
                        branch_info += (
                            f" ({metadata['commits_since_main']} commits ahead)"
                        )
                    response_parts.append(branch_info)

                # Add additional git metadata
                if metadata.get("has_uncommitted_changes"):
                    response_parts.append("⚠️ Had uncommitted changes")
                if metadata.get("is_merge_commit"):
                    response_parts.append("Type: Merge commit")

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
