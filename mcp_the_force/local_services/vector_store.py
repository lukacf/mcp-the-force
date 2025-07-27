"""Vector store lifecycle management."""

import asyncio
import logging
from typing import List, Optional, Dict, Tuple
from ..utils.vector_store import (
    create_vector_store,
    delete_vector_store,
    add_files_to_vector_store,
)
from ..utils.loiter_killer_client import LoiterKillerClient

logger = logging.getLogger(__name__)


# TEMPORARY: Simple in-memory replacement for Loiter Killer
class MockLoiterKiller:
    def __init__(self):
        self.enabled = True  # Pretend it's always enabled
        # Map session_id -> (vector_store_id, file_paths)
        self._sessions: Dict[str, Tuple[str, List[str]]] = {}

    async def get_or_create_vector_store(
        self, session_id: str
    ) -> Tuple[Optional[str], List[str]]:
        """Mock implementation that stores in memory."""
        if session_id in self._sessions:
            vs_id, file_paths = self._sessions[session_id]
            logger.info(
                f"[MOCK LK] Reusing vector store {vs_id} for session {session_id} with {len(file_paths)} files"
            )
            return vs_id, file_paths
        else:
            logger.info(f"[MOCK LK] No existing vector store for session {session_id}")
            return None, []

    async def track_files(self, session_id: str, file_paths: List[str]):
        """Mock implementation that updates in-memory tracking."""
        if session_id in self._sessions:
            vs_id, existing_paths = self._sessions[session_id]
            # Add new paths to existing ones
            all_paths = list(set(existing_paths + file_paths))
            self._sessions[session_id] = (vs_id, all_paths)
            logger.info(
                f"[MOCK LK] Updated session {session_id} with {len(file_paths)} new files, total: {len(all_paths)}"
            )
        else:
            logger.warning(
                f"[MOCK LK] Cannot track files for unknown session {session_id}"
            )

    def register_vector_store(self, session_id: str, vs_id: str, file_paths: List[str]):
        """Helper to register a newly created vector store."""
        self._sessions[session_id] = (vs_id, file_paths)
        logger.info(
            f"[MOCK LK] Registered vector store {vs_id} for session {session_id} with {len(file_paths)} files"
        )

    async def renew_lease(self, session_id: str):
        """Mock implementation of lease renewal."""
        logger.debug(f"[MOCK LK] Renewing lease for session {session_id}")
        # No-op for mock implementation
        pass


class VectorStoreManager:
    """Manages vector store creation and cleanup."""

    def __init__(self):
        self.loiter_killer = LoiterKillerClient()

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
        if not files:
            return None

        # Check if we're in mock mode
        from ..config import get_settings

        if get_settings().adapter_mock:
            # Return a mock vector store ID
            mock_vs_id = f"vs_mock_{session_id or 'ephemeral'}"
            logger.info(
                f"[MOCK] Created mock vector store: {mock_vs_id} with {len(files)} files"
            )
            return mock_vs_id

        # Try Loiter Killer first if session_id is available
        if session_id and self.loiter_killer.enabled:
            logger.info(f"Attempting to use Loiter Killer for session {session_id}")
            (
                vs_id,
                existing_file_paths,
            ) = await self.loiter_killer.get_or_create_vector_store(session_id)

            if vs_id:
                # Add only new files to the existing vector store
                uploaded_file_ids, skipped_files = await add_files_to_vector_store(
                    vs_id,
                    files,
                    existing_file_paths,  # Pass existing paths for proper deduplication
                )

                # Track the new files with Loiter Killer
                # Calculate which files were actually uploaded
                new_file_paths = [f for f in files if f not in skipped_files]
                if new_file_paths:
                    await self.loiter_killer.track_files(session_id, new_file_paths)
                    logger.info(
                        f"Added {len(new_file_paths)} new files to vector store {vs_id}"
                    )

                if skipped_files:
                    logger.info(
                        f"Skipped {len(skipped_files)} existing files in vector store {vs_id}"
                    )

                logger.info(
                    f"Using Loiter Killer vector store {vs_id} for session {session_id}"
                )
                return vs_id  # type: ignore[no-any-return]

        # Fallback to direct creation (Loiter Killer unavailable or no session_id)
        logger.info("Creating ephemeral vector store (Loiter Killer not available)")
        try:
            logger.info(
                f"VectorStoreManager.create: About to create vector store with {len(files)} files"
            )
            vs_id = await create_vector_store(files)
            logger.info(
                f"VectorStoreManager.create: vector store created, vs_id={vs_id}"
            )
            if vs_id:
                logger.info(f"Created vector store: {vs_id}")
                # Track the files with Loiter Killer for the new vector store
                if session_id and self.loiter_killer.enabled:
                    await self.loiter_killer.track_files(session_id, files)
            return vs_id  # type: ignore[no-any-return]
        except asyncio.CancelledError:
            # Don't swallow CancelledError - let it propagate
            logger.warning("VectorStoreManager.create cancelled")
            raise
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
        if self.loiter_killer.enabled:
            logger.debug(f"Skipping delete for Loiter Killer managed store: {vs_id}")
            return

        try:
            await delete_vector_store(vs_id)
            logger.info(f"Deleted ephemeral vector store: {vs_id}")
        except Exception as e:
            logger.error(f"Error deleting vector store: {e}")

    def get_all_for_session(self, session_id: str) -> List[str]:
        """Get all vector store IDs created for a session.

        This is used by attachment search to access all vector stores
        from the current session, not just the most recent one.

        Args:
            session_id: The session ID

        Returns:
            List of vector store IDs for the session
        """
        # Deprecated: Loiter Killer now manages vector store tracking
        return []


# Global instance
vector_store_manager = VectorStoreManager()
