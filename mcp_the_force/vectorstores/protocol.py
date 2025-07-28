"""Vector store protocol definitions.

This module defines the core protocols for vector stores:
- VSFile: Data class for files to be stored
- SearchResult: Data class for search results
- VectorStore: Protocol for vector store operations
- VectorStoreClient: Protocol for creating and managing vector stores
"""

from typing import Protocol, Sequence, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class VSFile(BaseModel):
    """A file to be stored in a vector store."""

    model_config = ConfigDict(frozen=True)

    path: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class SearchResult(BaseModel):
    """A search result from a vector store."""

    model_config = ConfigDict(frozen=True)

    file_id: str
    content: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VectorStore(Protocol):
    """Protocol for vector store operations.

    This is a minimal, intent-based interface. Implementations handle:
    - Batching (if provider has limits)
    - File format filtering (if provider has restrictions)
    - Error mapping to our exception hierarchy
    """

    @property
    def id(self) -> str:
        """Store ID."""
        ...

    @property
    def provider(self) -> str:
        """Provider name."""
        ...

    async def add_files(self, files: Sequence[VSFile]) -> Sequence[str]:
        """Add files to the vector store.

        Args:
            files: Files to add

        Returns:
            File IDs for the added files (same order as input)
        """
        ...

    async def delete_files(self, file_ids: Sequence[str]) -> None:
        """Delete files from the vector store.

        Args:
            file_ids: IDs of files to delete
        """
        ...

    async def search(
        self, query: str, k: int = 20, filter: Optional[Dict[str, Any]] = None
    ) -> Sequence[SearchResult]:
        """Search the vector store.

        Args:
            query: Search query
            k: Number of results to return
            filter: Optional metadata filter

        Returns:
            Search results ordered by relevance
        """
        ...


class VectorStoreClient(Protocol):
    """Protocol for creating and managing vector stores."""

    @property
    def provider(self) -> str:
        """Provider name."""
        ...

    async def create(self, name: str, ttl_seconds: Optional[int] = None) -> VectorStore:
        """Create a new vector store.

        Args:
            name: Name for the vector store
            ttl_seconds: Optional TTL in seconds (provider-dependent)

        Returns:
            Created vector store
        """
        ...

    async def get(self, store_id: str) -> VectorStore:
        """Get an existing vector store.

        Args:
            store_id: ID of the vector store

        Returns:
            Vector store instance
        """
        ...

    async def delete(self, store_id: str) -> None:
        """Delete a vector store.

        Args:
            store_id: ID of the vector store to delete
        """
        ...

    async def close(self) -> None:
        """Close the client and clean up resources."""
        ...
