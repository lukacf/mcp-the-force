"""File search implementation for Vertex/Gemini models.

This module implements the exact same file_search.msearch interface that OpenAI
models use, allowing Gemini to search vector stores with identical semantics.
"""

from typing import List, Dict, Any, Optional
import logging
import asyncio
from ..utils.vector_store import get_client as get_openai_client
from ..utils.thread_pool import get_shared_executor

logger = logging.getLogger(__name__)

# Thread pool for synchronous OpenAI calls (shared)
executor = get_shared_executor()

# Semaphore to limit concurrent searches
MAX_CONCURRENT_SEARCHES = 20
search_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)


class GeminiFileSearch:
    """Implements file_search.msearch for Gemini models."""

    def __init__(self, vector_store_ids: List[str]):
        """Initialize with vector store IDs to search.

        Args:
            vector_store_ids: List of OpenAI vector store IDs to search
        """
        self.vector_store_ids = vector_store_ids
        self._client = None

    @property
    def client(self):
        """Lazy-load OpenAI client."""
        if self._client is None:
            self._client = get_openai_client()
        return self._client

    async def msearch(self, queries: Optional[List[str]] = None) -> Dict[str, Any]:
        """Issues multiple queries to search over files.

        This matches OpenAI's file_search.msearch signature exactly.

        Args:
            queries: List of search queries (max 5). If None, returns empty results.

        Returns:
            Search results in the same format as OpenAI's file_search
        """
        if not queries or not self.vector_store_ids:
            return {"results": []}

        # Limit to 5 queries max (same as OpenAI)
        queries = queries[:5]

        # Execute all queries in parallel across all stores
        all_results: List[Dict[str, Any]] = []
        search_tasks: List[asyncio.Task[List[Dict[str, Any]]]] = []

        for query in queries:
            for store_id in self.vector_store_ids:
                task = asyncio.create_task(self._search_single_store(query, store_id))
                search_tasks.append(task)

        # Gather all results with timeout
        try:
            search_results: List[
                List[Dict[str, Any]] | BaseException
            ] = await asyncio.wait_for(
                asyncio.gather(*search_tasks, return_exceptions=True),
                timeout=3.0,  # 3 second timeout for all searches
            )
        except asyncio.TimeoutError:
            logger.warning("File search timed out after 3 seconds")
            search_results = []

        # Process results and handle exceptions
        for result in search_results:
            if isinstance(result, BaseException):
                logger.debug(f"Search error: {result}")
                continue
            if result and isinstance(result, list):
                all_results.extend(result)

        # Sort by relevance score and deduplicate
        seen_content: set[int] = set()
        unique_results: List[Dict[str, Any]] = []

        for search_result in sorted(
            all_results, key=lambda x: x.get("score", 0), reverse=True
        ):
            content_hash = hash(search_result.get("content", ""))
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_results.append(search_result)

        # Format results to match OpenAI's response structure
        formatted_results = []
        for i, unique_result in enumerate(unique_results[:40]):  # Match OpenAI's limit
            formatted_results.append(
                {
                    "text": unique_result.get("content", ""),
                    "metadata": {
                        "file_name": unique_result.get("file_name", "unknown"),
                        "score": unique_result.get("score", 0),
                        **unique_result.get("metadata", {}),
                    },
                    "citation": f"<source>{i}</source>",  # Citation marker format
                }
            )

        return {"results": formatted_results}

    async def _search_single_store(
        self, query: str, store_id: str
    ) -> List[Dict[str, Any]]:
        """Search a single vector store."""
        async with search_semaphore:  # Limit concurrent searches
            try:
                # OpenAI search is synchronous, run in thread pool
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    executor,
                    lambda: self.client.beta.vector_stores.search(
                        vector_store_id=store_id,
                        query=query,
                        max_num_results=40,  # Match OpenAI's default
                    ),
                )

                results: List[Dict[str, Any]] = []
                for item in response.data:
                    # Extract content text
                    content = ""
                    if hasattr(item, "content"):
                        if isinstance(item.content, list):
                            # Handle content blocks
                            for block in item.content:
                                if isinstance(block, dict) and "text" in block:
                                    content += block["text"] + "\n"
                                elif hasattr(block, "text"):
                                    content += block.text + "\n"
                        else:
                            content = str(item.content)

                    results.append(
                        {
                            "content": content.strip(),
                            "score": getattr(item, "score", 0),
                            "file_name": getattr(item, "file_name", "unknown"),
                            "file_id": getattr(item, "file_id", None),
                            "metadata": getattr(item, "metadata", {}),
                        }
                    )

                return results

            except Exception as e:
                logger.debug(f"Error searching store {store_id}: {e}")
                return []


def create_file_search_declaration():
    """Create the function declaration for Gemini.

    This matches OpenAI's file_search.msearch interface.
    """
    return {
        "name": "file_search_msearch",  # Flattened namespace for Gemini
        "description": (
            "Issues multiple queries to search over files and vector stores. "
            "Use this to find information in uploaded documents or project memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Array of search queries (max 5). Include the user's "
                        "original question plus focused queries for key terms."
                    ),
                    "maxItems": 5,
                }
            },
            "required": [],  # queries is optional, matching OpenAI
        },
    }
