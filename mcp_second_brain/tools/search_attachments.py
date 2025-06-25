"""Search session attachments tool implementation.

This provides a way for models to search ephemeral vector stores created
from attachments during the current execution.
"""

from typing import List, Dict, Any
import logging
import asyncio
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from ..config import get_settings
from ..adapters.base import BaseAdapter
from .base import ToolSpec
from .descriptors import Route
from .registry import tool

logger = logging.getLogger(__name__)

# Context variable to track current execution's ephemeral vector stores
current_attachment_stores: ContextVar[List[str]] = ContextVar(
    "current_attachment_stores", default=[]
)

# Thread pool for synchronous OpenAI operations
executor = ThreadPoolExecutor(max_workers=3)

# Semaphore to limit concurrent searches
search_semaphore = asyncio.Semaphore(3)


@tool
class SearchSessionAttachments(ToolSpec):
    """Search ephemeral attachment vector stores for current session."""

    model_name = "attachment_search"
    adapter_class = "SearchAttachmentAdapter"
    context_window = 0  # Not applicable for search
    timeout = 20  # 20 second timeout for searches

    # Parameters
    query: str = Route.prompt(description="Search query or semicolon-separated queries")  # type: ignore
    max_results: int = Route.prompt(
        description="Maximum results to return (default: 20)"
    )  # type: ignore


class SearchAttachmentAdapter(BaseAdapter):
    """Adapter for searching ephemeral attachment stores."""

    model_name = "attachment_search"
    context_window = 0  # Not applicable
    description_snippet = "Search current session attachments"

    def __init__(self, model_name: str = "attachment_search"):
        self.model_name = model_name
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key)

    async def generate(
        self,
        prompt: str,
        vector_store_ids: List[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Search attachment stores and return formatted results.

        This searches only the ephemeral stores created for the current
        execution's attachments.
        """
        # Extract search parameters
        query = kwargs.get("query", prompt)
        max_results = kwargs.get("max_results", 20)

        if not query:
            return "Error: Search query is required"

        # Get current execution's attachment stores
        attachment_stores = current_attachment_stores.get()
        if not attachment_stores:
            return "No attachments available to search in this session"

        try:
            # Support multiple queries (semicolon-separated)
            queries = (
                [q.strip() for q in query.split(";") if q.strip()]
                if ";" in query
                else [query]
            )

            # Search all attachment stores in parallel
            search_tasks = []
            for store_id in attachment_stores:
                for q in queries:
                    task = self._search_single_store(
                        q, store_id, max_results // max(len(queries), 1)
                    )
                    search_tasks.append(task)

            # Wait for all searches with timeout
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*search_tasks, return_exceptions=True),
                    timeout=10.0,  # 10 second timeout for all searches
                )
            except asyncio.TimeoutError:
                logger.warning("Attachment search timed out")
                return "Attachment search timed out after 10 seconds"

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
                return f"No results found in attachments for query: '{query}'"

            # Build formatted response
            response_parts = [
                f"Found {len(all_results)} results in session attachments:"
            ]

            for i, search_result in enumerate(all_results, 1):
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
            logger.error(f"Attachment search failed: {e}")
            return f"Error searching attachments: {str(e)}"

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
                logger.error(f"Failed to search attachment store {store_id}: {e}")
                raise
