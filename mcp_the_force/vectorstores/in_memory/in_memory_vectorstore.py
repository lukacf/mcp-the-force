"""In-memory vector store implementation for testing."""

import uuid
from typing import Dict, List, Sequence, Optional, Any, Tuple
from datetime import datetime
import asyncio

from ..protocol import VectorStore, VSFile, SearchResult
from ..errors import UnsupportedFeatureError


class InMemoryVectorStore:
    """In-memory vector store implementation."""

    def __init__(
        self,
        store_id: str,
        name: str,
        ttl_seconds: Optional[int] = None,
        max_batch_size: Optional[int] = None,
        max_file_size_mb: Optional[float] = None,
    ):
        self.id = store_id
        self.provider = "inmemory"
        self.name = name
        self._ttl_seconds = ttl_seconds
        self._max_batch_size = max_batch_size
        self._max_file_size_mb = max_file_size_mb

        # Storage
        self._files: Dict[str, Tuple[VSFile, str]] = {}  # file_id -> (file, content)
        self._file_id_counter = 0
        self._lock = asyncio.Lock()
        self._supports_filtering: Optional[bool] = None

        # TTL tracking
        self._created_at = datetime.now().timestamp()
        if ttl_seconds:
            self._expires_at: Optional[float] = self._created_at + ttl_seconds
        else:
            self._expires_at: Optional[float] = None

    async def add_files(self, files: Sequence[VSFile]) -> Sequence[str]:
        """Add files to the store."""
        async with self._lock:
            file_ids = []

            # Handle batching if needed
            if self._max_batch_size:
                # Process in batches
                for i in range(0, len(files), self._max_batch_size):
                    batch = files[i : i + self._max_batch_size]
                    batch_ids = await self._add_batch(batch)
                    file_ids.extend(batch_ids)
            else:
                file_ids = await self._add_batch(files)

            return file_ids

    async def _add_batch(self, files: Sequence[VSFile]) -> List[str]:
        """Add a batch of files."""
        file_ids = []

        for file in files:
            # Check file size limit
            if self._max_file_size_mb:
                size_mb = len(file.content.encode("utf-8")) / (1024 * 1024)
                if size_mb > self._max_file_size_mb:
                    # Skip oversized files
                    continue

            # Generate file ID
            self._file_id_counter += 1
            file_id = f"file_{self._file_id_counter}"

            # Store file
            self._files[file_id] = (
                file,
                file.content.lower(),
            )  # Store lowercase for search
            file_ids.append(file_id)

        return file_ids

    async def delete_files(self, file_ids: Sequence[str]) -> None:
        """Delete files from the store."""
        async with self._lock:
            for file_id in file_ids:
                self._files.pop(file_id, None)

    async def search(
        self, query: str, k: int = 20, filter: Optional[Dict[str, Any]] = None
    ) -> Sequence[SearchResult]:
        """Search for files matching the query."""
        if filter and not hasattr(self, "_supports_filtering"):
            raise UnsupportedFeatureError("Filtering not supported")

        async with self._lock:
            results = []
            query_lower = query.lower()
            query_words = set(query_lower.split())

            for file_id, (file, content_lower) in self._files.items():
                # Apply metadata filter if provided
                if filter:
                    if not file.metadata:
                        continue

                    # Check all filter conditions
                    match = True
                    for key, value in filter.items():
                        if key not in file.metadata or file.metadata[key] != value:
                            match = False
                            break

                    if not match:
                        continue

                # Calculate relevance score
                score = 0.0

                # Check for substring match first
                if query_lower in content_lower:
                    # Count occurrences
                    count = content_lower.count(query_lower)
                    score = min(2.0, 1.0 + (count / 100.0))
                else:
                    # Word overlap scoring
                    content_words = content_lower.split()
                    content_word_set = set(content_words)
                    overlap = len(query_words & content_word_set)

                    if overlap == 0:
                        continue

                    # Base score on overlap
                    score = overlap / len(query_words)

                    # Add bonus for exact phrase match
                    if query_lower in content_lower:
                        score += 0.5

                    # Add bonus for term frequency
                    for word in query_words:
                        count = content_words.count(word)
                        if count > 1:
                            score += 0.1 * (count - 1)  # Bonus for repeated words

                # Add result if we have a score
                if score > 0:
                    results.append(
                        SearchResult(
                            file_id=file_id,
                            content=file.content,
                            score=score,
                            metadata=file.metadata or {},
                        )
                    )

            # Sort by score descending
            results.sort(key=lambda r: r.score, reverse=True)

            # Return top k
            return results[:k]


class InMemoryClient:
    """In-memory vector store client."""

    def __init__(
        self,
        max_batch_size: Optional[int] = None,
        max_file_size_mb: Optional[float] = None,
        supports_filtering: bool = True,
    ):
        self.provider = "inmemory"
        self._stores: Dict[str, InMemoryVectorStore] = {}
        self._closed = False
        self._max_batch_size = max_batch_size
        self._max_file_size_mb = max_file_size_mb
        self._supports_filtering = supports_filtering

    async def create(self, name: str, ttl_seconds: Optional[int] = None) -> VectorStore:
        """Create a new vector store."""
        if self._closed:
            raise RuntimeError("Client is closed")

        store_id = f"inmem_{uuid.uuid4().hex[:8]}"
        store = InMemoryVectorStore(
            store_id=store_id,
            name=name,
            ttl_seconds=ttl_seconds,
            max_batch_size=self._max_batch_size,
            max_file_size_mb=self._max_file_size_mb,
        )

        if self._supports_filtering:
            store._supports_filtering = True

        self._stores[store_id] = store
        return store

    async def get(self, store_id: str) -> VectorStore:
        """Get an existing vector store."""
        if self._closed:
            raise RuntimeError("Client is closed")

        if store_id not in self._stores:
            raise KeyError(f"Store not found: {store_id}")

        return self._stores[store_id]

    async def delete(self, store_id: str) -> None:
        """Delete a vector store."""
        if self._closed:
            raise RuntimeError("Client is closed")

        self._stores.pop(store_id, None)

    async def close(self) -> None:
        """Close the client."""
        self._closed = True
        self._stores.clear()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
