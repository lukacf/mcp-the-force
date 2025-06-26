"""Search project memory tool implementation.

This provides a unified way for all models (OpenAI and Gemini) to search
across project memory stores without the 2-store limitation.
"""

from typing import List, Dict, Any, TYPE_CHECKING
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

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

# Thread pool for synchronous OpenAI operations
executor = ThreadPoolExecutor(max_workers=5)

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
    query: str = Route.prompt(description="Search query or semicolon-separated queries")  # type: ignore
    max_results: int = Route.prompt(
        description="Maximum results to return (default: 40)"
    )  # type: ignore
    store_types: List[str] = Route.prompt(  # type: ignore
        description="Types of stores to search (default: ['conversation', 'commit'])"
    )


class SearchMemoryAdapter(BaseAdapter):
    """Adapter for searching project memory stores."""

    model_name = "memory_search"
    context_window = 0  # Not applicable
    description_snippet = "Search project memory stores"

    def __init__(self, model_name: str = "memory_search"):
        self.model_name = model_name
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.memory_config = get_memory_config()

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
        max_results = kwargs.get("max_results", 40)
        store_types = kwargs.get("store_types", ["conversation", "commit"])

        if not query:
            return "Error: Search query is required"

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
                return "Memory search timed out after 10 seconds"

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

            # Limit total results
            all_results = all_results[:max_results]

            # Format response
            if not all_results:
                return f"No results found for query: '{query}'"

            # Build formatted response with metadata
            response_parts = [
                f"Found {len(all_results)} results across {len(stores_to_search)} memory stores:"
            ]

            for i, search_result in enumerate(all_results, 1):
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
            return f"Error searching memory: {str(e)}"

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

                    # Add metadata if available
                    if hasattr(item, "metadata") and item.metadata:
                        result["metadata"] = item.metadata

                    results.append(result)

                return results

            except Exception as e:
                logger.error(f"Failed to search store {store_id}: {e}")
                raise
