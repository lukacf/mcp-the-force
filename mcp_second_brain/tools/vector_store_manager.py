"""Vector store lifecycle management."""

import asyncio
import logging
from typing import List, Optional
from ..utils.vector_store import create_vector_store, delete_vector_store

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """Manages vector store creation and cleanup."""

    async def create(self, files: List[str]) -> Optional[str]:
        """Create vector store from files.

        Args:
            files: List of file paths

        Returns:
            Vector store ID if created, None otherwise
        """
        if not files:
            return None

        try:
            logger.info(
                f"VectorStoreManager.create: About to call asyncio.to_thread with {len(files)} files"
            )
            vs_id = await asyncio.to_thread(create_vector_store, files)
            logger.info(
                f"VectorStoreManager.create: asyncio.to_thread returned vs_id={vs_id}"
            )
            if vs_id:
                logger.info(f"Created vector store: {vs_id}")
            return vs_id
        except Exception as e:
            logger.error(f"Error creating vector store: {e}", exc_info=True)
            return None

    async def delete(self, vs_id: Optional[str]) -> None:
        """Delete vector store.

        Args:
            vs_id: Vector store ID to delete
        """
        if not vs_id:
            return

        try:
            await asyncio.to_thread(delete_vector_store, vs_id)
            logger.info(f"Deleted vector store: {vs_id}")
        except Exception as e:
            logger.error(f"Error deleting vector store: {e}")


# Global instance
vector_store_manager = VectorStoreManager()
