"""Async wrapper for MemoryConfig to handle blocking operations."""

import asyncio
from typing import Optional, List
from pathlib import Path

from .config import MemoryConfig
from ..adapters.openai.client import OpenAIClientFactory
from ..config import get_settings
from ..utils.loiter_killer_client import LoiterKillerClient

import logging

logger = logging.getLogger(__name__)


class AsyncMemoryConfig:
    """Async wrapper around MemoryConfig to handle blocking operations."""

    def __init__(self, db_path: Optional[Path] = None):
        self._sync_config = MemoryConfig(db_path)
        self._loiter_killer = LoiterKillerClient()

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
            logger.info(f"[MEMORY] Using existing store: {store_id}")

            # Verify the store actually exists in OpenAI
            settings = get_settings()
            client = await OpenAIClientFactory.get_instance(
                api_key=settings.openai_api_key
            )

            try:
                # Try to retrieve the store to verify it exists
                await client.vector_stores.retrieve(store_id)
                logger.info(f"[MEMORY] Verified store {store_id} exists in OpenAI")
            except Exception as e:
                # Store doesn't exist in OpenAI - mark for creation
                logger.warning(
                    f"[MEMORY] Store {store_id} not found in OpenAI: {e}. Will create new store."
                )
                need_create = True
                # Fall through to creation logic below

            if not need_create:
                # Store exists - register with LoiterKiller if needed
                session_id = "project-memory-conversation"
                logger.info(
                    f"[MEMORY] Checking if existing store {store_id} needs LoiterKiller registration..."
                )
                try:
                    registered = await self._loiter_killer.register_existing_store(
                        session_id, store_id, protected=True
                    )
                    if registered:
                        logger.info(
                            f"[MEMORY] Successfully registered existing store {store_id} with LoiterKiller"
                        )
                    else:
                        logger.debug(
                            f"[MEMORY] Store {store_id} already registered or LoiterKiller unavailable"
                        )
                except Exception as e:
                    logger.debug(
                        f"[MEMORY] Could not register existing store {store_id}: {e}"
                    )
                return str(store_id)

        # Need to create a new store - do this async
        logger.info(f"[MEMORY] Need to create new store (current: {store_id})")
        settings = get_settings()
        client = await OpenAIClientFactory.get_instance(api_key=settings.openai_api_key)

        if not store_id:
            # No stores exist, create first one
            name = "project-conversations-001"
            logger.info(f"[MEMORY] Creating first conversation store: {name}")
            store = await client.vector_stores.create(
                name=name, expires_after={"anchor": "last_active_at", "days": 365}
            )
            logger.info(f"[MEMORY] Created conversation store: {store.id}")

            # Register with LoiterKiller as protected project memory
            session_id = "project-memory-conversation"
            logger.info(
                f"[MEMORY] Attempting to register store {store.id} with LoiterKiller..."
            )
            try:
                registered = await self._loiter_killer.register_existing_store(
                    session_id, store.id, protected=True
                )
                if registered:
                    logger.info(
                        f"[MEMORY] Successfully registered store {store.id} with LoiterKiller"
                    )
                else:
                    logger.warning(
                        f"[MEMORY] Failed to register store {store.id} with LoiterKiller"
                    )
            except Exception as e:
                logger.error(
                    f"[MEMORY] Exception registering store {store.id} with LoiterKiller: {e}"
                )

            # Record in DB
            def _record_store():
                with self._sync_config._lock:
                    with self._sync_config._db:
                        self._sync_config._db.execute(
                            """
                            INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active)
                            VALUES (?, 'conversation', 0, datetime('now'), 1)
                        """,
                            (store.id,),
                        )

            await loop.run_in_executor(None, _record_store)
            return str(store.id)
        else:
            # Need to rollover
            return await self._rollover_store_async("conversation")

    async def _rollover_store_async(self, store_type: str) -> str:
        """Create new store and mark it as active (async version)."""
        loop = self._get_loop()

        # Get store count from DB
        def _get_count():
            with self._sync_config._lock:
                count = self._sync_config._db.execute(
                    "SELECT COUNT(*) FROM stores WHERE store_type = ?", (store_type,)
                ).fetchone()[0]
                return count

        count = await loop.run_in_executor(None, _get_count)
        new_num = count + 1

        # Create new store via async API
        settings = get_settings()
        client = await OpenAIClientFactory.get_instance(api_key=settings.openai_api_key)

        name = f"project-{store_type}s-{new_num:03d}"
        store = await client.vector_stores.create(
            name=name, expires_after={"anchor": "last_active_at", "days": 365}
        )

        # Register with LoiterKiller as protected project memory
        session_id = f"project-memory-{store_type}"
        logger.info(
            f"[MEMORY] Attempting to register store {store.id} with LoiterKiller..."
        )
        try:
            registered = await self._loiter_killer.register_existing_store(
                session_id, store.id, protected=True
            )
            if registered:
                logger.info(
                    f"[MEMORY] Successfully registered store {store.id} with LoiterKiller"
                )
            else:
                logger.warning(
                    f"[MEMORY] Failed to register store {store.id} with LoiterKiller"
                )
        except Exception as e:
            logger.error(
                f"[MEMORY] Exception registering store {store.id} with LoiterKiller: {e}"
            )

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
                        (store.id, store_type),
                    )

        await loop.run_in_executor(None, _update_db)

        logger.info(f"Created new {store_type} store: {store.id} (#{new_num})")
        return str(store.id)

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
            logger.info(f"[MEMORY] Using existing store: {store_id}")

            # Verify the store actually exists in OpenAI
            settings = get_settings()
            client = await OpenAIClientFactory.get_instance(
                api_key=settings.openai_api_key
            )

            try:
                # Try to retrieve the store to verify it exists
                await client.vector_stores.retrieve(store_id)
                logger.info(f"[MEMORY] Verified store {store_id} exists in OpenAI")
            except Exception as e:
                # Store doesn't exist in OpenAI - mark for creation
                logger.warning(
                    f"[MEMORY] Store {store_id} not found in OpenAI: {e}. Will create new store."
                )
                need_create = True
                # Fall through to creation logic below

            if not need_create:
                # Store exists - register with LoiterKiller if needed
                session_id = "project-memory-commit"
                logger.info(
                    f"[MEMORY] Checking if existing store {store_id} needs LoiterKiller registration..."
                )
                try:
                    registered = await self._loiter_killer.register_existing_store(
                        session_id, store_id, protected=True
                    )
                    if registered:
                        logger.info(
                            f"[MEMORY] Successfully registered existing store {store_id} with LoiterKiller"
                        )
                    else:
                        logger.debug(
                            f"[MEMORY] Store {store_id} already registered or LoiterKiller unavailable"
                        )
                except Exception as e:
                    logger.debug(
                        f"[MEMORY] Could not register existing store {store_id}: {e}"
                    )
                return str(store_id)

        # Need to create a new store - do this async
        logger.info(f"[MEMORY] Need to create new store (current: {store_id})")
        settings = get_settings()
        client = await OpenAIClientFactory.get_instance(api_key=settings.openai_api_key)

        if not store_id:
            # No stores exist, create first one
            name = "project-commits-001"
            store = await client.vector_stores.create(
                name=name, expires_after={"anchor": "last_active_at", "days": 365}
            )

            # Register with LoiterKiller as protected project memory
            session_id = "project-memory-commit"
            logger.info(
                f"[MEMORY] Attempting to register store {store.id} with LoiterKiller..."
            )
            try:
                registered = await self._loiter_killer.register_existing_store(
                    session_id, store.id, protected=True
                )
                if registered:
                    logger.info(
                        f"[MEMORY] Successfully registered store {store.id} with LoiterKiller"
                    )
                else:
                    logger.warning(
                        f"[MEMORY] Failed to register store {store.id} with LoiterKiller"
                    )
            except Exception as e:
                logger.error(
                    f"[MEMORY] Exception registering store {store.id} with LoiterKiller: {e}"
                )

            # Record in DB
            def _record_store():
                with self._sync_config._lock:
                    with self._sync_config._db:
                        self._sync_config._db.execute(
                            """
                            INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active)
                            VALUES (?, 'commit', 0, datetime('now'), 1)
                        """,
                            (store.id,),
                        )

            await loop.run_in_executor(None, _record_store)
            return str(store.id)
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
