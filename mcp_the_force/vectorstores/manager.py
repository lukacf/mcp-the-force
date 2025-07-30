"""High-level vector store manager for orchestration."""

import asyncio
import hashlib
import logging
from typing import Dict, Any, List, Tuple, Optional, Sequence, Union
from pathlib import Path

from .protocol import VectorStore, VectorStoreClient, VSFile, SearchResult
from . import registry
from ..vector_store_cache import VectorStoreCache
from ..utils.stable_list_cache import StableListCache

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """High-level manager for vector store operations.

    Handles:
    - Store creation and lifecycle
    - Integration with loiter killer for cleanup
    - File update detection and management
    - Provider-agnostic vector store operations
    """

    def __init__(
        self, cache: Optional[StableListCache] = None, provider: Optional[str] = None
    ):
        from ..config import get_settings

        settings = get_settings()
        self.provider = provider or settings.mcp.default_vector_store_provider

        # Initialize vector store cache with settings
        db_path = getattr(settings, "session_db_path", ".mcp_sessions.sqlite3")
        ttl = (
            getattr(settings.vector_stores, "ttl_seconds", 7200)
            if hasattr(settings, "vector_stores")
            else 7200
        )
        purge_prob = (
            getattr(settings.vector_stores, "cleanup_probability", 0.02)
            if hasattr(settings, "vector_stores")
            else 0.02
        )

        self.vector_store_cache = VectorStoreCache(
            db_path=db_path, ttl=ttl, purge_probability=purge_prob
        )

        self._cache = cache  # For future use
        self._client_cache: Dict[str, VectorStoreClient] = {}

    def _read_file_content(self, file_path: str) -> str:
        """Read file content from disk."""
        try:
            return Path(file_path).read_text()
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return ""

    def _get_client(self, provider: str) -> VectorStoreClient:
        """Get or create a client for the provider."""
        if provider not in self._client_cache:
            self._client_cache[provider] = registry.get_client(provider)
        return self._client_cache[provider]

    def _get_client_for_store(self, provider: str) -> VectorStoreClient:
        """Get client for store operations, handling mock mode.

        In mock mode, always returns inmemory client regardless of provider.
        """
        from ..config import get_settings

        if get_settings().adapter_mock:
            return self._get_client("inmemory")
        return self._get_client(provider)

    def _compute_file_hash(self, content: str) -> str:
        """Compute hash for file content."""
        return hashlib.sha256(content.encode()).hexdigest()

    async def create(
        self,
        files: List[str],
        session_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> Optional[Union[str, Dict[str, Any]]]:
        """Create or acquire vector store from files.

        Args:
            files: List of file paths
            session_id: Session ID for vector store reuse
            ttl_seconds: Optional TTL for the vector store

        Returns:
            Vector store ID if created, None otherwise
        """
        # Allow empty files for session creation
        # if not files:
        #     return None

        # Check if we're in mock mode
        from ..config import get_settings

        if get_settings().adapter_mock:
            # In mock mode, use in-memory provider for implementation
            # but preserve the original provider name for compatibility
            original_provider = self.provider
            mock_client = self._get_client("inmemory")

            # Create a real in-memory store that can be retrieved
            store_name = f"mock_{session_id or 'ephemeral'}"
            store = await mock_client.create(store_name, ttl_seconds=ttl_seconds)

            logger.info(
                f"[MOCK] Created in-memory vector store: {store.id} for provider {original_provider} with {len(files)} files"
            )

            # Add files if provided
            if files:
                vs_files = []
                for file_path in files:
                    content = self._read_file_content(file_path)
                    if content:  # Only add if we could read the file
                        vs_files.append(VSFile(path=file_path, content=content))

                if vs_files:
                    await store.add_files(vs_files)

            return {
                "store_id": store.id,
                "provider": original_provider,  # Return the originally requested provider
                "session_id": session_id,
            }

        provider = self.provider
        client = self._get_client(provider)

        # Check for existing vector store in cache
        existing_store_id = None
        was_reused = False

        if session_id:
            (
                existing_store_id,
                was_reused,
            ) = await self.vector_store_cache.get_or_create_placeholder(
                session_id, provider
            )

            if existing_store_id:
                logger.info(
                    f"Reusing existing vector store {existing_store_id} for session {session_id}"
                )
                # Just return the existing store ID, files are already there
                return existing_store_id

        # Create new vector store
        logger.info(
            f"Creating new vector store for session {session_id or 'ephemeral'}"
        )
        try:
            logger.info(
                f"VectorStoreManager.create: About to create vector store with {len(files)} files"
            )

            # Create store
            store = await client.create(
                name=f"session_{session_id}" if session_id else "mcp-the-force-vs",
                ttl_seconds=ttl_seconds,
            )

            # Convert file paths to VSFile objects
            vs_files = []
            for file_path in files:
                content = self._read_file_content(file_path)
                if content:  # Only add if we could read the file
                    vs_files.append(VSFile(path=file_path, content=content))

            if vs_files:
                await store.add_files(vs_files)
                logger.info(
                    f"Added {len(vs_files)} files to new vector store {store.id}"
                )

            # Register with cache for lifecycle management
            if session_id:
                await self.vector_store_cache.register_store(
                    session_id, store.id, provider
                )

            logger.info(f"Created vector store: {store.id}")
            return {
                "store_id": store.id,
                "provider": provider,
                "session_id": session_id,
            }

        except Exception as e:
            logger.error(f"Error creating vector store: {e}", exc_info=True)
            return None

    async def delete(self, vs_id: Optional[str]) -> None:
        """Delete vector store (only for ephemeral stores).

        Args:
            vs_id: Vector store ID to delete
        """
        if not vs_id:
            return

        # Check if we're in mock mode
        from ..config import get_settings

        if get_settings().adapter_mock:
            # In mock mode, actually delete from inmemory client
            try:
                client = self._get_client("inmemory")
                await client.delete(vs_id)
                logger.info(f"[MOCK] Deleted mock vector store: {vs_id}")
            except Exception as e:
                logger.error(f"[MOCK] Error deleting mock vector store: {e}")
            return

        # Don't delete cache-managed stores - they handle their own lifecycle
        # The cleanup task will handle deletion when appropriate
        logger.debug(f"Vector store {vs_id} lifecycle is managed by cache")
        return

    async def create_for_session(
        self,
        session_id: str,
        ttl_seconds: Optional[int] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a vector store for a session.

        This method is kept for compatibility with tests but delegates to create().
        """
        # For now, just create a store using the main create method
        files: List[str] = []  # Empty files for session creation
        result = await self.create(files, session_id, ttl_seconds)

        # If create returned None (error), return empty dict
        if result is None:
            return {}

        # If it's already a dict (new behavior), return it with provider override if needed
        if isinstance(result, dict):
            if provider:
                result["provider"] = provider
            return result

        # Legacy: if it returned just a string ID
        return {
            "provider": provider or self.provider,
            "store_id": result,
            "session_id": session_id,
        }

    async def store_and_search(
        self,
        session_id: str,
        files: List[Tuple[str, str]],
        query: str,
        ttl_seconds: Optional[int] = None,
        k: int = 20,
    ) -> Sequence[SearchResult]:
        """Store files and immediately search them.

        Args:
            session_id: Session identifier
            files: List of (path, content) tuples
            query: Search query
            ttl_seconds: Optional TTL
            k: Number of results

        Returns:
            Search results
        """
        # Create store
        store_info = await self.create_for_session(
            session_id=session_id, ttl_seconds=ttl_seconds
        )

        # Get store
        client = self._get_client_for_store(store_info["provider"])
        store = await client.get(store_info["store_id"])

        # Convert to VSFile objects
        vs_files = [VSFile(path=path, content=content) for path, content in files]

        # Add files
        await store.add_files(vs_files)

        # Search
        return await store.search(query, k=k)

    async def create_overflow_store(
        self, session_id: str, files: List[Tuple[str, str]], ttl_seconds: int = 1800
    ) -> Dict[str, Any]:
        """Create a store for context overflow.

        Args:
            session_id: Session identifier
            files: Large files that overflow context
            ttl_seconds: TTL (default 30 minutes)

        Returns:
            Store info
        """
        # Create store
        store_info = await self.create_for_session(
            session_id=f"overflow_{session_id}", ttl_seconds=ttl_seconds
        )

        # Add files
        client = self._get_client_for_store(store_info["provider"])
        store = await client.get(store_info["store_id"])

        vs_files = [VSFile(path=path, content=content) for path, content in files]

        await store.add_files(vs_files)

        return store_info

    async def search_overflow(
        self, store_info: Dict[str, Any], query: str, k: int = 20
    ) -> Sequence[SearchResult]:
        """Search an overflow store.

        Args:
            store_info: Store info from create_overflow_store
            query: Search query
            k: Number of results

        Returns:
            Search results
        """
        client = self._get_client_for_store(store_info["provider"])
        store = await client.get(store_info["store_id"])
        return await store.search(query, k=k)

    async def store_files_with_updates(
        self,
        session_id: str,
        files: List[Tuple[str, str]],
        store_info: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Store files with update detection.

        Args:
            session_id: Session identifier
            files: List of (path, content) tuples
            store_info: Existing store info (if updating)
            ttl_seconds: TTL for new stores

        Returns:
            Store info
        """
        # Create or get store
        if not store_info:
            store_info = await self.create_for_session(
                session_id=session_id, ttl_seconds=ttl_seconds
            )

        client = self._get_client(store_info["provider"])
        store = await client.get(store_info["store_id"])

        # If we have a cache, handle updates
        if self._cache:
            # TODO: Implement vector store file cache tracking
            # The StableListCache needs methods to track file hash -> vector_file_id mappings
            # For now, we'll just add all files without update detection
            pass

        # For now, always add all files (no update detection)
        if True:  # Was: else:
            # No cache - just add all files
            vs_files = [VSFile(path=path, content=content) for path, content in files]
            await store.add_files(vs_files)

        return store_info

    async def _delete_and_add_file(
        self, path: str, new_content: str, store: VectorStore, old_file_id: str
    ):
        """Delete old version and add new version of a file.

        This is used by tests to verify update behavior.
        """
        await store.delete_files([old_file_id])
        file = VSFile(path=path, content=new_content)
        await store.add_files([file])

    async def cleanup_expired(self) -> int:
        """Clean up expired vector stores.

        Returns:
            Number of stores cleaned up
        """
        logger.info("Starting vector store cleanup")
        cleaned_count = 0

        # Get expired stores from cache
        expired_stores = await self.vector_store_cache.get_expired_stores(limit=100)

        if not expired_stores:
            logger.debug("No expired vector stores to clean up")
            return 0

        # Group by provider for efficient batch deletion
        stores_by_provider: Dict[str, List[Dict[str, Any]]] = {}
        for store in expired_stores:
            provider = store["provider"]
            if provider not in stores_by_provider:
                stores_by_provider[provider] = []
            stores_by_provider[provider].append(store)

        # Delete stores for each provider
        for provider, stores in stores_by_provider.items():
            client = self._get_client(provider)

            # Create deletion tasks
            delete_tasks = []
            for store in stores:

                async def delete_store(store_info):
                    try:
                        await client.delete(store_info["vector_store_id"])
                        return store_info["session_id"], True
                    except Exception as e:
                        logger.error(
                            f"Failed to delete vector store {store_info['vector_store_id']}: {e}"
                        )
                        return store_info["session_id"], False

                delete_tasks.append(delete_store(store))

            # Execute deletions concurrently
            results = await asyncio.gather(*delete_tasks, return_exceptions=True)

            # Remove successfully deleted stores from cache
            for result in results:
                if isinstance(result, tuple) and result[1]:
                    session_id = result[0]
                    if await self.vector_store_cache.remove_store(session_id):
                        cleaned_count += 1

        logger.info(f"Cleaned up {cleaned_count} expired vector stores")

        # Also clean up orphaned entries (older than 30 days)
        orphaned_count = await self.vector_store_cache.cleanup_orphaned()
        if orphaned_count > 0:
            logger.info(f"Cleaned up {orphaned_count} orphaned cache entries")

        return cleaned_count

    async def renew_lease(self, session_id: str) -> bool:
        """Renew the lease for a vector store.

        Args:
            session_id: The session identifier

        Returns:
            True if lease was renewed, False if not found
        """
        return await self.vector_store_cache.renew_lease(session_id)


# Global instance
vector_store_manager = VectorStoreManager()
