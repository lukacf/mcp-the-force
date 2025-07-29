"""High-level vector store manager for orchestration."""

import hashlib
import logging
from typing import Dict, Any, List, Tuple, Optional, Sequence
from pathlib import Path

from .protocol import VectorStore, VectorStoreClient, VSFile, SearchResult
from . import registry
from ..utils.loiter_killer_client import LoiterKillerClient
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
        self.loiter_killer = LoiterKillerClient()
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

    def _compute_file_hash(self, content: str) -> str:
        """Compute hash for file content."""
        return hashlib.sha256(content.encode()).hexdigest()

    async def create(
        self, files: List[str], session_id: Optional[str] = None
    ) -> Optional[str]:
        """Create or acquire vector store from files.

        Args:
            files: List of file paths
            session_id: Session ID for vector store reuse

        Returns:
            Vector store ID if created, None otherwise
        """
        # Allow empty files for session creation
        # if not files:
        #     return None

        # Check if we're in mock mode
        from ..config import get_settings

        if get_settings().adapter_mock:
            # Return a mock vector store ID
            mock_vs_id = f"vs_mock_{session_id or 'ephemeral'}"
            logger.info(
                f"[MOCK] Created mock vector store: {mock_vs_id} with {len(files)} files"
            )
            return mock_vs_id

        provider = self.provider
        client = self._get_client(provider)

        # Try Loiter Killer first if session_id is available and provider is OpenAI
        if session_id and self.loiter_killer.enabled and provider == "openai":
            logger.info(f"Attempting to use Loiter Killer for session {session_id}")
            (
                vs_id,
                existing_file_paths,
            ) = await self.loiter_killer.get_or_create_vector_store(session_id)

            if vs_id:
                # Get existing store and add only new files
                store = await client.get(vs_id)

                # Find new files to add
                new_files = [f for f in files if f not in existing_file_paths]

                if new_files:
                    # Convert to VSFile objects
                    vs_files = []
                    for file_path in new_files:
                        content = self._read_file_content(file_path)
                        if content:  # Only add if we could read the file
                            vs_files.append(VSFile(path=file_path, content=content))

                    if vs_files:
                        await store.add_files(vs_files)
                        # Track the new files with Loiter Killer
                        await self.loiter_killer.track_files(session_id, new_files)
                        logger.info(
                            f"Added {len(new_files)} new files to vector store {vs_id}"
                        )

                skipped_files = [f for f in files if f in existing_file_paths]
                if skipped_files:
                    logger.info(
                        f"Skipped {len(skipped_files)} existing files in vector store {vs_id}"
                    )

                logger.info(
                    f"Using Loiter Killer vector store {vs_id} for session {session_id}"
                )
                return vs_id

        # Fallback to direct creation (Loiter Killer unavailable or no session_id)
        logger.info("Creating ephemeral vector store (Loiter Killer not available)")
        try:
            logger.info(
                f"VectorStoreManager.create: About to create vector store with {len(files)} files"
            )

            # Create store
            store = await client.create(
                name=f"session_{session_id}" if session_id else "mcp-the-force-vs"
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

            # Track with Loiter Killer for OpenAI stores
            if session_id and self.loiter_killer.enabled and provider == "openai":
                await self.loiter_killer.track_files(session_id, files)

            logger.info(f"Created vector store: {store.id}")
            return store.id

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
            logger.info(f"[MOCK] Deleted mock vector store: {vs_id}")
            return

        # Don't delete Loiter Killer managed stores - they handle their own lifecycle
        if self.loiter_killer.enabled and self.provider == "openai":
            logger.debug(f"Skipping delete for Loiter Killer managed store: {vs_id}")
            return

        try:
            client = self._get_client(self.provider)
            await client.delete(vs_id)
            logger.info(f"Deleted ephemeral vector store: {vs_id}")
        except Exception as e:
            logger.error(f"Error deleting vector store: {e}")

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
        vs_id = await self.create(files, session_id)

        return {
            "provider": provider or self.provider,
            "store_id": vs_id,
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
        client = self._get_client(store_info["provider"])
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
        client = self._get_client(store_info["provider"])
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
        client = self._get_client(store_info["provider"])
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


# Global instance
vector_store_manager = VectorStoreManager()
