"""Vector store lifecycle management."""

import asyncio
import logging
import collections
from typing import List, Optional, Dict
from ..utils.vector_store import create_vector_store, delete_vector_store
from ..utils.vector_store_files import add_files_to_vector_store
from ..utils.loiter_killer_client import LoiterKillerClient

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """Manages vector store creation and cleanup."""

    def __init__(self):
        self.loiter_killer = LoiterKillerClient()
        # Track all vector stores created for a session (for attachment search)
        self._session_vs: Dict[str, List[str]] = collections.defaultdict(list)

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

        # Try Loiter Killer first if session_id is available
        if session_id and self.loiter_killer.enabled:
            logger.info(f"Attempting to use Loiter Killer for session {session_id}")
            (
                vs_id,
                existing_file_paths,
            ) = await self.loiter_killer.get_or_create_vector_store(session_id)

            if vs_id:
                # Track this vector store for the session
                if vs_id not in self._session_vs[session_id]:
                    self._session_vs[session_id].append(vs_id)

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
                return vs_id

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
                # Track even ephemeral stores if we have a session_id
                if session_id and vs_id not in self._session_vs[session_id]:
                    self._session_vs[session_id].append(vs_id)
            return vs_id
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
        return list(self._session_vs.get(session_id, []))


# Global instance
vector_store_manager = VectorStoreManager()
