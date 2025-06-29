"""Common deduplication functionality for search tools."""

import hashlib
import asyncio
from typing import Dict, Any, List, Set
import logging

logger = logging.getLogger(__name__)


class SearchDeduplicator:
    """Manages deduplication for search results across multiple searches."""

    def __init__(self, cache_name: str = "search"):
        """Initialize deduplicator with a named cache."""
        self.cache_name = cache_name
        self._dedup_cache: Set[str] = set()
        self._dedup_lock = asyncio.Lock()

    @staticmethod
    def compute_content_hash(content: str, file_id: str = "") -> str:
        """Compute a hash for deduplication based on content and file_id."""
        # Include both content and file_id to handle same content from different files
        combined = f"{content}:{file_id}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    async def clear_cache(self):
        """Clear the deduplication cache."""
        async with self._dedup_lock:
            self._dedup_cache.clear()
        logger.info(f"Cleared {self.cache_name} deduplication cache")

    async def deduplicate_results(
        self, all_results: List[Dict[str, Any]], max_results: int
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Deduplicate search results based on content hash.

        Args:
            all_results: List of search results to deduplicate
            max_results: Maximum number of results to return

        Returns:
            Tuple of (deduplicated_results, duplicate_count)
        """
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

                content_hash = self.compute_content_hash(content, file_id)

                # Check if we've seen this content before
                if content_hash not in self._dedup_cache:
                    self._dedup_cache.add(content_hash)
                    deduplicated_results.append(search_result)

                    # Stop when we have enough results
                    if len(deduplicated_results) >= max_results:
                        break
                else:
                    duplicate_count += 1

        return deduplicated_results, duplicate_count


def extract_file_id_from_result(result: Dict[str, Any]) -> str:
    """Extract file_id from various result formats."""
    if "file_id" in result:
        return str(result["file_id"])
    elif "metadata" in result and isinstance(result["metadata"], dict):
        return str(result["metadata"].get("file_id", ""))
    return ""
