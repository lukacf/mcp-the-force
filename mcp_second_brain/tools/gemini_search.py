"""Gemini file search tool for querying OpenAI vector stores."""

from typing import Optional, List, Dict, Any
from ..utils.vector_store import get_client
from ..memory import get_memory_config
from .base import ToolSpec
from .descriptors import Route
from .registry import tool
import logging

logger = logging.getLogger(__name__)


@tool
class SearchProjectMemory(ToolSpec):
    """Search project memory (conversations and commits) for Gemini models.

    This tool allows Gemini models to search OpenAI vector stores,
    giving them access to the same project memory as OpenAI models.
    """

    query: str = Route.prompt(pos=0, description="Search query")
    branch_filter: Optional[str] = Route.prompt(
        description="Optional: Filter results to specific git branch"
    )
    result_limit: Optional[int] = Route.adapter(
        default=10, description="Maximum number of results to return (default: 10)"
    )

    async def execute(self) -> str:
        """Search vector stores and return formatted results."""
        try:
            # Get all memory store IDs
            memory_config = get_memory_config()
            store_ids = memory_config.get_all_store_ids()

            if not store_ids:
                return "No project memory stores found. Project memory may not be initialized yet."

            # Get OpenAI client
            client = get_client()

            # Build filters if branch specified
            filters = None
            if self.branch_filter:
                filters = {"type": "eq", "key": "branch", "value": self.branch_filter}

            # Search all stores
            all_results = []
            for store_id in store_ids:
                try:
                    results = client.vector_stores.search(
                        vector_store_id=store_id,
                        query=self.query,
                        max_num_results=self.result_limit or 10,
                        filters=filters,
                    )

                    # Add results with store context
                    for result in results.data:
                        all_results.append(
                            {
                                "store_id": store_id,
                                "score": result.score,
                                "content": result.content,
                                "metadata": getattr(result, "metadata", {}),
                            }
                        )

                except Exception as e:
                    logger.warning(f"Failed to search store {store_id}: {e}")
                    continue

            # Sort by score
            all_results.sort(key=lambda x: x["score"], reverse=True)

            # Limit results
            all_results = all_results[: self.result_limit or 10]

            # Format results
            return self._format_results(all_results)

        except Exception as e:
            logger.error(f"Error in SearchProjectMemory: {e}")
            return f"Error searching project memory: {str(e)}"

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """Format search results for Gemini."""
        if not results:
            return f"No results found for query: '{self.query}'"

        formatted = f"# Project Memory Search Results\n\nQuery: '{self.query}'\n"
        if self.branch_filter:
            formatted += f"Branch filter: {self.branch_filter}\n"
        formatted += f"\nFound {len(results)} results:\n\n"

        for i, result in enumerate(results, 1):
            formatted += f"## Result {i} (Score: {result['score']:.3f})\n"

            # Add metadata if available
            metadata = result.get("metadata", {})
            if metadata:
                mem_type = metadata.get("type", "unknown")
                formatted += f"Type: {mem_type}\n"

                if mem_type == "conversation":
                    formatted += f"Tool: {metadata.get('tool', 'N/A')}\n"
                    formatted += f"Session: {metadata.get('session_id', 'N/A')}\n"
                elif mem_type == "commit":
                    formatted += f"Commit: {metadata.get('commit_sha', 'N/A')[:8]}\n"
                    formatted += (
                        f"Files: {', '.join(metadata.get('files_changed', [])[:3])}\n"
                    )

                formatted += f"Branch: {metadata.get('branch', 'N/A')}\n"
                formatted += f"Date: {metadata.get('datetime', 'N/A')}\n"

            # Add content
            formatted += "\n### Content\n"
            if result.get("content"):
                # Handle different content formats
                content = result["content"]
                if isinstance(content, list) and content:
                    # OpenAI returns list of content blocks
                    text = (
                        content[0].get("text", "")
                        if isinstance(content[0], dict)
                        else str(content[0])
                    )
                    formatted += text[:500]  # Limit length
                    if len(text) > 500:
                        formatted += "..."
                else:
                    formatted += str(content)[:500]

            formatted += "\n\n---\n\n"

        return formatted


# Optional: Simpler search for just conversations or commits
@tool
class SearchConversations(ToolSpec):
    """Search only AI consultation conversations."""

    query: str = Route.prompt(pos=0, description="Search query")
    tool_filter: Optional[str] = Route.prompt(
        description="Filter by tool name (e.g., 'chat_with_o3')"
    )

    async def execute(self) -> str:
        """Search conversation stores only."""
        # Delegate to SearchProjectMemory with type filter
        search_tool = SearchProjectMemory()
        search_tool.query = self.query
        search_tool.branch_filter = None
        search_tool.result_limit = 10

        # Would need to modify SearchProjectMemory to support type filters
        # For now, just use the general search
        result = await search_tool.execute()

        # Post-filter for conversations
        if "Type: conversation" in result:
            return result
        else:
            return f"No conversation results found for: '{self.query}'"


@tool
class SearchCommits(ToolSpec):
    """Search only git commits."""

    query: str = Route.prompt(pos=0, description="Search query")
    branch: Optional[str] = Route.prompt(description="Filter by git branch")

    async def execute(self) -> str:
        """Search commit stores only."""
        # Delegate to SearchProjectMemory
        search_tool = SearchProjectMemory()
        search_tool.query = self.query
        search_tool.branch_filter = self.branch
        search_tool.result_limit = 10

        # Would need to modify SearchProjectMemory to support type filters
        # For now, just use the general search with branch filter
        return await search_tool.execute()
