"""HNSW vector store implementation using HNSWLib."""

import asyncio
import json
import os
import uuid
import numpy as np
from pathlib import Path
from typing import Sequence, Dict, Any, Optional, List, Callable, Protocol
from threading import Lock

from ..protocol import VectorStore, VectorStoreClient, VSFile, SearchResult
from ..errors import VectorStoreError
from .embedding import get_embedding_model, get_embedding_dimensions
from .chunker import chunk_text_by_paragraph

# Define a shared persistence directory for all HNSW stores
PERSISTENCE_DIR = Path.home() / ".cache" / "mcp-the-force" / "vectorstores" / "hnsw"


class IndexProtocol(Protocol):
    """Protocol for HNSW index implementations."""

    def init_index(self, max_elements: int, ef_construction: int, M: int) -> None: ...
    def add_items(self, vectors: np.ndarray, ids: List[int]) -> None: ...
    def get_current_count(self) -> int: ...
    def knn_query(
        self, queries: np.ndarray, k: int
    ) -> tuple[List[List[int]], List[List[float]]]: ...
    def save_index(self, path: str) -> None: ...
    def load_index(self, path: str, max_elements: int) -> None: ...


def _default_index_factory(dim: int) -> IndexProtocol:  # pragma: no cover
    """Default factory that creates real hnswlib indices."""
    import hnswlib

    idx = hnswlib.Index(space="cosine", dim=dim)
    # Don't initialize here - let the store handle it with proper sizing
    return idx  # type: ignore[no-any-return]


class HnswVectorStore(VectorStore):
    """HNSW vector store instance."""

    def __init__(
        self,
        client: "HnswVectorStoreClient",
        store_id: str,
        *,
        index_factory: Callable[[int], IndexProtocol] = _default_index_factory,
        persist: bool = True,
    ):
        self.client = client
        self._id = store_id
        self._provider = "hnsw"
        self._index: Optional[IndexProtocol] = None
        self._doc_chunks: List[Dict[str, str]] = []  # {'text': str, 'source': str}
        self._lock = Lock()
        self._index_factory = index_factory
        self._persist = persist
        self._max_elements = 10000  # Initial capacity

    @property
    def id(self) -> str:
        """Store ID."""
        return self._id

    @property
    def provider(self) -> str:
        """Provider name."""
        return self._provider

    async def add_files(self, files: Sequence[VSFile]) -> Sequence[str]:
        """Add files to the vector store."""
        if not files:
            return []

        # Process files and prepare chunks outside the lock
        all_chunks = []
        all_metadata = []

        for file in files:
            # Chunk the file content
            chunks = chunk_text_by_paragraph(file.content)

            # Store metadata for each chunk
            for chunk in chunks:
                all_chunks.append(chunk)
                all_metadata.append({"text": chunk, "source": file.path})

        if not all_chunks:
            return []

        # Generate embeddings outside the lock (run in executor to avoid blocking asyncio)
        model = get_embedding_model()
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: model.encode(
                all_chunks,
                batch_size=32,
                convert_to_numpy=True,
                show_progress_bar=False,
            ),
        )

        # Now acquire the lock for index operations
        with self._lock:
            # Lazy initialize the index
            if self._index is None:
                self._index = self._index_factory(get_embedding_dimensions())
                self._index.init_index(
                    max_elements=self._max_elements, ef_construction=200, M=16
                )

            # Check if we need to resize the index
            current_count = len(self._doc_chunks)
            new_count = current_count + len(all_chunks)

            if new_count > self._max_elements:
                # Double the capacity (with some headroom)
                new_max = max(new_count * 2, self._max_elements * 2)
                try:
                    # Resize the index (this is supported by hnswlib)
                    self._index.resize_index(new_max)  # type: ignore
                    self._max_elements = new_max
                except AttributeError:
                    # If resize is not supported (e.g., in tests), log warning
                    import logging

                    logging.warning(
                        f"Index resize not supported, may hit capacity limit at {self._max_elements} elements"
                    )

            # Add to index
            start_idx = current_count
            indices = list(range(start_idx, start_idx + len(all_chunks)))
            self._index.add_items(embeddings, indices)

            # Store metadata
            self._doc_chunks.extend(all_metadata)

            # Return file IDs (using indices as IDs for now)
            file_ids = [f"file_{i}" for i in range(len(files))]

            # Save to disk if persistence is enabled
            if self._persist:
                self._save()

            return file_ids

    async def delete_files(self, file_ids: Sequence[str]) -> None:
        """Delete files from the vector store.

        Note: HNSW doesn't support deletion of individual vectors efficiently.
        This is a limitation of the underlying library. For now, this is a no-op.
        A full implementation would require rebuilding the entire index.
        """
        # TODO: Implement proper deletion by rebuilding index without deleted items
        # For now, we acknowledge the limitation
        pass

    async def search(
        self, query: str, k: int = 20, filter: Optional[Dict[str, Any]] = None
    ) -> Sequence[SearchResult]:
        """Search the vector store."""
        with self._lock:
            if not self._index or self._index.get_current_count() == 0:
                return []

        # 1. Embed the query (run in executor to avoid blocking asyncio)
        model = get_embedding_model()
        loop = asyncio.get_running_loop()
        query_vector = await loop.run_in_executor(
            None,
            lambda: model.encode(
                [query], convert_to_numpy=True, show_progress_bar=False
            ),
        )

        # 2. Query the HNSW index
        # This is a blocking CPU-bound call, so run in an executor
        with self._lock:
            if not self._index:  # Additional safety check
                return []
            # Capture index reference to avoid mypy union type issues
            index = self._index
            labels, distances = await loop.run_in_executor(
                None,
                lambda: index.knn_query(
                    query_vector, k=min(k, index.get_current_count())
                ),
            )

        # 3. Map the resulting labels (IDs) back to the stored chunks
        results = []
        for i, label in enumerate(labels[0]):
            chunk_meta = self._doc_chunks[label]
            results.append(
                SearchResult(
                    file_id=str(label),  # The index in our metadata list
                    content=chunk_meta["text"],
                    score=1.0 - distances[0][i],  # Convert distance to similarity score
                    metadata={"source": chunk_meta["source"]},
                )
            )
        return results

    def _save(self) -> None:
        """Save the index and metadata to disk atomically."""
        # Ensure the persistence directory exists
        try:
            self.client.persistence_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            raise VectorStoreError(
                f"Cannot create persistence directory {self.client.persistence_dir}: {e}"
            ) from e

        index_path = self.client.persistence_dir / f"{self._id}.bin"
        meta_path = self.client.persistence_dir / f"{self._id}.json"

        # Note: This method should only be called when the lock is already held
        # by the calling method (e.g., add_files), so we don't acquire it here
        if not self._index:
            return

        # Write to temporary files first for atomicity
        # Note: with_suffix replaces the ENTIRE suffix, so we need to be careful
        index_tmp = self.client.persistence_dir / f"{self._id}.bin.tmp"
        meta_tmp = self.client.persistence_dir / f"{self._id}.json.tmp"

        try:
            # Save the HNSW index
            self._index.save_index(str(index_tmp))
        except (RuntimeError, OSError, PermissionError) as e:
            index_tmp.unlink(missing_ok=True)
            raise VectorStoreError(f"Failed to save HNSW index: {e}") from e

        try:
            # Save the metadata
            import logging

            logging.debug(
                f"Saving metadata to {meta_tmp}, doc_chunks={len(self._doc_chunks)}"
            )
            with open(meta_tmp, "w") as f:
                json.dump(self._doc_chunks, f)
            logging.debug(f"Metadata saved, file exists: {meta_tmp.exists()}")
        except (OSError, PermissionError) as e:
            # Clean up both temp files
            index_tmp.unlink(missing_ok=True)
            meta_tmp.unlink(missing_ok=True)
            raise VectorStoreError(f"Failed to save metadata: {e}") from e

        try:
            # Atomically move the files
            os.rename(str(index_tmp), str(index_path))
            os.rename(str(meta_tmp), str(meta_path))
        except (OSError, PermissionError) as e:
            # Clean up temp files on error
            index_tmp.unlink(missing_ok=True)
            meta_tmp.unlink(missing_ok=True)
            raise VectorStoreError(
                f"Failed to move files to final location: {e}"
            ) from e


class HnswVectorStoreClient(VectorStoreClient):
    """Client for creating and managing HNSW vector stores."""

    def __init__(
        self,
        *,
        index_factory: Callable[[int], IndexProtocol] = _default_index_factory,
        persist: bool = True,
    ):
        self._provider = "hnsw"
        self.persistence_dir = PERSISTENCE_DIR
        self._lock = Lock()
        self._index_factory = index_factory
        self._persist = persist

    @property
    def provider(self) -> str:
        """Provider name."""
        return self._provider

    async def create(self, name: str, ttl_seconds: Optional[int] = None) -> VectorStore:
        """Create a new vector store."""
        store_id = f"hnsw_{uuid.uuid4().hex[:8]}"
        store = HnswVectorStore(
            client=self,
            store_id=store_id,
            index_factory=self._index_factory,
            persist=self._persist,
        )

        # Initialize empty store and save it immediately if persistence is enabled
        # This ensures the store exists on disk even before any files are added
        if self._persist:
            # Initialize the index with default parameters
            store._index = store._index_factory(get_embedding_dimensions())
            store._index.init_index(
                max_elements=store._max_elements, ef_construction=200, M=16
            )
            store._save()

        return store

    async def get(self, store_id: str) -> VectorStore:
        """Get an existing vector store."""
        index_path = self.persistence_dir / f"{store_id}.bin"
        meta_path = self.persistence_dir / f"{store_id}.json"

        if not index_path.exists() or not meta_path.exists():
            raise VectorStoreError(f"Store with ID {store_id} not found on disk.")

        # Create a new store instance to populate
        store = HnswVectorStore(
            client=self,
            store_id=store_id,
            index_factory=self._index_factory,
            persist=self._persist,
        )

        try:
            # Load metadata
            try:
                with open(meta_path, "r") as f:
                    store._doc_chunks = json.load(f)
            except FileNotFoundError:
                raise VectorStoreError(f"Metadata file not found for store {store_id}")
            except PermissionError as e:
                raise VectorStoreError(
                    f"Permission denied reading metadata for store {store_id}: {e}"
                ) from e
            except json.JSONDecodeError as e:
                raise VectorStoreError(
                    f"Corrupted metadata file for store {store_id}: {e}"
                ) from e

            # Load HNSW index
            if store._doc_chunks:  # Only load index if there are chunks
                try:
                    store._index = store._index_factory(get_embedding_dimensions())
                    # Load with a larger max_elements to allow growth
                    current_elements = len(store._doc_chunks)
                    max_elements = max(current_elements * 2, 10000)
                    store._index.load_index(str(index_path), max_elements=max_elements)
                    store._max_elements = max_elements
                    # Set ef for better search performance
                    # ef controls speed/accuracy tradeoff (higher = more accurate but slower)
                    store._index.set_ef(50)  # type: ignore[attr-defined]  # Default is 10, we use 50 for better accuracy
                except FileNotFoundError:
                    raise VectorStoreError(f"Index file not found for store {store_id}")
                except (RuntimeError, OSError) as e:
                    raise VectorStoreError(
                        f"Failed to load HNSW index for store {store_id}: {e}"
                    ) from e

            return store
        except VectorStoreError:
            # Re-raise our own errors
            raise
        except Exception as e:
            # Catch any unexpected errors
            raise VectorStoreError(
                f"Unexpected error loading store {store_id}: {e}"
            ) from e

    async def delete(self, store_id: str) -> None:
        """Delete a vector store and its associated files."""
        index_path = self.persistence_dir / f"{store_id}.bin"
        meta_path = self.persistence_dir / f"{store_id}.json"

        # Delete files if they exist (no error if missing)
        try:
            if index_path.exists():
                index_path.unlink()
        except (OSError, PermissionError):
            # Log but don't fail - best effort cleanup
            pass

        try:
            if meta_path.exists():
                meta_path.unlink()
        except (OSError, PermissionError):
            # Log but don't fail - best effort cleanup
            pass

    async def close(self) -> None:
        """Close the client."""
        pass
