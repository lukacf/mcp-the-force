"""Search task files tool implementation.

This provides a way for models to search ephemeral vector stores created
from overflow files during the current execution.
"""

from typing import List, Dict, Any
import logging
import asyncio

from openai import AsyncOpenAI
import fastmcp.exceptions

# No longer need BaseAdapter - this is a local service
from ..adapters.openai.client import OpenAIClientFactory
from .base import ToolSpec
from .descriptors import Route
from .registry import tool
from .search_dedup import SearchDeduplicator

logger = logging.getLogger(__name__)

# Semaphore to limit concurrent searches
search_semaphore = asyncio.Semaphore(3)


@tool
class SearchTaskFiles(ToolSpec):
    """Search task files in vector stores for current session."""

    model_name = "task_files_search"
    adapter_class = "SearchTaskFilesAdapter"
    context_window = 0  # Not applicable for search
    timeout = 20  # 20 second timeout for searches

    # Parameters
    query = Route.prompt(description="Search query or semicolon-separated queries")  # type: ignore[assignment]
    max_results = Route.prompt(  # type: ignore[assignment]
        description="Maximum results to return (default: 20)",
        default=20,
    )
    vector_store_ids = Route.vector_store_ids(  # type: ignore[assignment]
        default_factory=list,
        description="IDs of vector stores to search",
    )


class SearchTaskFilesAdapter:
    """Local service for searching task files in vector stores."""

    model_name = "task_files_search"
    context_window = 0  # Not applicable
    description_snippet = "Search current session task files"

    # Class-level deduplicator shared across instances
    _deduplicator = SearchDeduplicator("task_files")

    def __init__(self, model_name: str = "task_files_search"):
        self.model_name = model_name
        # Client will be obtained asynchronously via _get_client()

    async def _get_client(self) -> AsyncOpenAI:
        """Get the OpenAI client instance using the singleton factory."""
        return await OpenAIClientFactory.get_instance()

    @classmethod
    async def clear_deduplication_cache(cls):
        """Clear the deduplication cache."""
        await cls._deduplicator.clear_cache()

    async def execute(self, **kwargs) -> str:
        """Execute method for local service compatibility."""
        # Extract the necessary parameters for generate
        query = kwargs.get("query", "")
        vector_store_ids = kwargs.get("vector_store_ids", [])

        # Call generate with the appropriate parameters
        return await self.generate(
            prompt=query, vector_store_ids=vector_store_ids, **kwargs
        )

    async def generate(
        self,
        prompt: str,
        vector_store_ids: List[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Search task files in vector stores and return formatted results.

        This searches only the vector stores provided via ``vector_store_ids``.
        """
        # Extract search parameters
        query = kwargs.get("query", prompt)
        max_results = kwargs.get("max_results", 20)

        logger.info(
            f"[SEARCH_TASK_FILES] Query: '{query}', Max results: {max_results}, "
            f"Vector stores: {len(vector_store_ids) if vector_store_ids else 0}"
        )

        if not query:
            raise fastmcp.exceptions.ToolError("Search query is required")

        # Use provided vector store IDs
        task_file_stores = vector_store_ids or []
        if not task_file_stores:
            return "No task files available to search in this session"

        try:
            # Support multiple queries (semicolon-separated)
            queries = (
                [q.strip() for q in query.split(";") if q.strip()]
                if ";" in query
                else [query]
            )

            # Search all task file stores in parallel
            search_tasks = []
            for store_id in task_file_stores:
                for q in queries:
                    # Ensure each query gets at least 1 result slot
                    per_query_limit = max(1, max_results // max(len(queries), 1))
                    task = self._search_single_store(q, store_id, per_query_limit)
                    search_tasks.append(task)

            # Wait for all searches with timeout
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*search_tasks, return_exceptions=True),
                    timeout=30.0,  # 30 second timeout for all searches
                )
            except asyncio.TimeoutError:
                logger.warning("Task file search timed out")
                raise fastmcp.exceptions.ToolError(
                    "Task file search timed out after 30 seconds"
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

            logger.info(
                f"[SEARCH_TASK_FILES] Search completed. Total results: {len(all_results)}, "
                f"Errors: {errors}, Queries: {queries}"
            )

            # Sort by relevance score
            all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

            # Apply deduplication
            (
                deduplicated_results,
                duplicate_count,
            ) = await self._deduplicator.deduplicate_results(all_results, max_results)

            # Format response
            if not deduplicated_results:
                logger.warning(
                    f"[SEARCH_TASK_FILES] No results after deduplication. "
                    f"Total before: {len(all_results)}, Duplicates: {duplicate_count}, "
                    f"Query: '{query}'"
                )
                return f"No results found in task files for query: '{query}'"

            # Build formatted response
            response_parts = [
                f"Found {len(deduplicated_results)} results in session task files:"
            ]

            for i, search_result in enumerate(deduplicated_results, 1):
                response_parts.append(f"\n--- Result {i} ---")
                response_parts.append(f"Score: {search_result.get('score', 'N/A')}")

                # Add file name if available in metadata
                metadata = search_result.get("metadata", {})
                if metadata.get("filename"):
                    response_parts.append(f"File: {metadata['filename']}")

                # Add content
                content = search_result.get("content", "")
                # Truncate very long content
                if len(content) > 1000:
                    content = content[:1000] + "..."
                response_parts.append(f"Content: {content}")

            if errors > 0:
                response_parts.append(f"\nNote: {errors} searches failed")

            return "\n".join(response_parts)

        except Exception as e:
            logger.error(f"Task file search failed: {e}")
            raise fastmcp.exceptions.ToolError(f"Error searching task files: {e}")

    async def _search_single_store(
        self, query: str, store_id: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Search a single vector store."""
        async with search_semaphore:  # Limit concurrent searches
            try:
                # Get the async client from singleton factory
                client = await self._get_client()

                # Use the async vector store search method
                response = await client.vector_stores.search(
                    vector_store_id=store_id,
                    query=query,
                    max_num_results=max_results,
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

                logger.info(
                    f"[SEARCH_TASK_FILES] Store {store_id} returned {len(results)} results "
                    f"for query: '{query}'"
                )
                return results

            except Exception as e:
                logger.error(f"Failed to search task file store {store_id}: {e}")
                raise
