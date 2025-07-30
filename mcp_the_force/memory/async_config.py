"""Async wrapper for MemoryConfig to handle blocking operations."""

import asyncio
from typing import Optional, List
from pathlib import Path

from .config import MemoryConfig
from ..vectorstores.manager import vector_store_manager

import logging

logger = logging.getLogger(__name__)


class AsyncMemoryConfig:
    """Async wrapper around MemoryConfig to handle blocking operations."""

    def __init__(self, db_path: Optional[Path] = None):
        self._sync_config = MemoryConfig(db_path)

    def _get_loop(self):
        """Get the current event loop."""
        return asyncio.get_running_loop()

    async def get_active_conversation_store(self) -> str:
        """Get active conversation store ID, creating if needed (async)."""
        loop = self._get_loop()

        # First check if we have an active store (quick DB operation)
        def _check_active():
            with self._sync_config._lock:
                store_id, count = self._sync_config._get_active_store("conversation")
                if store_id and count < self._sync_config._rollover_limit:
                    return str(store_id), False  # No need to create
                return str(store_id), True  # Need to create or rollover

        store_id, need_create = await loop.run_in_executor(None, _check_active)

        if not need_create:
            logger.debug(f"[MEMORY] Using existing store: {store_id}")

            # Verify the store actually exists in the vector store provider
            try:
                # Try to retrieve the store to verify it exists
                provider = vector_store_manager.provider
                client = vector_store_manager._get_client(provider)
                await client.get(store_id)
                logger.debug(f"[MEMORY] Verified store {store_id} exists in {provider}")
            except Exception as e:
                # Store doesn't exist in provider - mark for creation
                logger.warning(
                    f"[MEMORY] Store {store_id} not found in {provider}: {e}. Will create new store."
                )
                need_create = True
                # Fall through to creation logic below

            if not need_create:
                # Store exists and is valid
                return str(store_id)

        # Need to create a new store - do this async
        logger.info(f"[MEMORY] Need to create new store (current: {store_id})")

        if not store_id:
            # No stores exist, create first one
            name = "project-conversations-001"
            logger.info(f"[MEMORY] Creating first conversation store: {name}")

            # Use VectorStoreManager to create the store
            result = await vector_store_manager.create(
                files=[], name=name, protected=True
            )

            if not result:
                raise RuntimeError("Failed to create vector store")

            # Extract store_id from result
            store_id = result.get("store_id") if isinstance(result, dict) else result
            logger.info(f"[MEMORY] Created conversation store: {store_id}")

            # Record in DB
            def _record_store():
                with self._sync_config._lock:
                    with self._sync_config._db:
                        self._sync_config._db.execute(
                            """
                            INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active)
                            VALUES (?, 'conversation', 0, datetime('now'), 1)
                        """,
                            (store_id,),
                        )

            await loop.run_in_executor(None, _record_store)
            return str(store_id)
        else:
            # Need to rollover
            return await self._rollover_store_async("conversation")

    async def _rollover_store_async(self, store_type: str) -> str:
        """Create new store and mark it as active (async version)."""
        loop = self._get_loop()

        # Get store count and current active store from DB
        def _get_count_and_current():
            with self._sync_config._lock:
                count = self._sync_config._db.execute(
                    "SELECT COUNT(*) FROM stores WHERE store_type = ?", (store_type,)
                ).fetchone()[0]

                # Get the current active store id for rollover_from
                current_store = self._sync_config._db.execute(
                    "SELECT store_id FROM stores WHERE store_type = ? AND is_active = 1",
                    (store_type,),
                ).fetchone()
                current_store_id = current_store[0] if current_store else None

                return count, current_store_id

        count, current_store_id = await loop.run_in_executor(
            None, _get_count_and_current
        )
        new_num = count + 1

        # Create new store via VectorStoreManager
        name = f"project-{store_type}s-{new_num:03d}"

        logger.info(
            f"[MEMORY] Creating rollover store: {name} (from {current_store_id})"
        )

        # Use VectorStoreManager to create the store with rollover_from
        result = await vector_store_manager.create(
            files=[], name=name, protected=True, rollover_from=current_store_id
        )

        if not result:
            raise RuntimeError("Failed to create rollover vector store")

        # Extract store_id from result
        store_id = result.get("store_id") if isinstance(result, dict) else result

        # The memory module's DB update below will mark old stores as inactive

        # Update DB
        def _update_db():
            with self._sync_config._lock:
                with self._sync_config._db:
                    # Deactivate old stores
                    self._sync_config._db.execute(
                        "UPDATE stores SET is_active = 0 WHERE store_type = ?",
                        (store_type,),
                    )
                    # Insert new active store
                    self._sync_config._db.execute(
                        """
                        INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active)
                        VALUES (?, ?, 0, datetime('now'), 1)
                    """,
                        (store_id, store_type),
                    )

        await loop.run_in_executor(None, _update_db)

        logger.info(f"Created new {store_type} store: {store_id} (#{new_num})")
        return str(store_id)

    async def get_active_commit_store(self) -> str:
        """Get active commit store ID, creating if needed (async)."""
        loop = self._get_loop()

        # First check if we have an active store (quick DB operation)
        def _check_active():
            with self._sync_config._lock:
                store_id, count = self._sync_config._get_active_store("commit")
                if store_id and count < self._sync_config._rollover_limit:
                    return str(store_id), False  # No need to create
                return str(store_id), True  # Need to create or rollover

        store_id, need_create = await loop.run_in_executor(None, _check_active)

        if not need_create:
            logger.debug(f"[MEMORY] Using existing store: {store_id}")

            # Verify the store actually exists in the vector store provider
            try:
                # Try to retrieve the store to verify it exists
                provider = vector_store_manager.provider
                client = vector_store_manager._get_client(provider)
                await client.get(store_id)
                logger.debug(f"[MEMORY] Verified store {store_id} exists in {provider}")
            except Exception as e:
                # Store doesn't exist in provider - mark for creation
                logger.warning(
                    f"[MEMORY] Store {store_id} not found in {provider}: {e}. Will create new store."
                )
                need_create = True
                # Fall through to creation logic below

            if not need_create:
                # Store exists and is valid
                return str(store_id)

        # Need to create a new store - do this async
        logger.info(f"[MEMORY] Need to create new store (current: {store_id})")

        if not store_id:
            # No stores exist, create first one
            name = "project-commits-001"
            logger.info(f"[MEMORY] Creating first commit store: {name}")

            # Use VectorStoreManager to create the store
            result = await vector_store_manager.create(
                files=[], name=name, protected=True
            )

            if not result:
                raise RuntimeError("Failed to create vector store")

            # Extract store_id from result
            store_id = result.get("store_id") if isinstance(result, dict) else result
            logger.info(f"[MEMORY] Created commit store: {store_id}")

            # Record in DB
            def _record_store():
                with self._sync_config._lock:
                    with self._sync_config._db:
                        self._sync_config._db.execute(
                            """
                            INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active)
                            VALUES (?, 'commit', 0, datetime('now'), 1)
                        """,
                            (store_id,),
                        )

            await loop.run_in_executor(None, _record_store)
            return str(store_id)
        else:
            # Need to rollover
            return await self._rollover_store_async("commit")

    def increment_conversation_count(self):
        """Increment document count for active conversation store."""
        # This is a quick DB operation, can stay sync
        self._sync_config.increment_conversation_count()

    def get_all_store_ids(self) -> List[str]:
        """Get all store IDs for querying."""
        # This is a quick DB operation, can stay sync
        return self._sync_config.get_all_store_ids()

    def get_store_ids_by_type(self, store_types: List[str]) -> List[str]:
        """Get store IDs filtered by type."""
        # This is a quick DB operation, can stay sync
        return self._sync_config.get_store_ids_by_type(store_types)


# Global async config instance
_async_memory_config: Optional[AsyncMemoryConfig] = None


def get_async_memory_config() -> AsyncMemoryConfig:
    """Get the global async memory configuration instance."""
    global _async_memory_config
    if _async_memory_config is None:
        _async_memory_config = AsyncMemoryConfig()
    return _async_memory_config
