"""Radical state reset utilities to prevent cross-query contamination."""

import asyncio
import gc
import sys
import logging
from typing import Any

logger = logging.getLogger(__name__)


class StateResetManager:
    """Manages aggressive state reset between tool executions."""

    def __init__(self):
        self._execution_count = 0
        self._singletons_to_clear = []  # Use list instead of set
        self._reset_callbacks = []

    def register_singleton(self, singleton_dict: dict, key: Any = None):
        """Register a singleton dictionary to be cleared on reset."""
        # Store direct reference - we'll handle WeakKeyDictionary specially
        self._singletons_to_clear.append(singleton_dict)

    def register_reset_callback(self, callback):
        """Register a callback to be called during reset."""
        self._reset_callbacks.append(callback)

    async def reset_all_state(self):
        """Aggressively reset all state between queries."""
        logger.warning("[STATE RESET] Starting aggressive state reset")

        # 1. Cancel ALL pending tasks except the current one
        current_task = asyncio.current_task()
        all_tasks = asyncio.all_tasks()
        tasks_to_cancel = [t for t in all_tasks if t != current_task and not t.done()]

        if tasks_to_cancel:
            logger.warning(
                f"[STATE RESET] Cancelling {len(tasks_to_cancel)} pending tasks"
            )
            for task in tasks_to_cancel:
                task.cancel()

            # Wait briefly for cancellations to complete
            await asyncio.sleep(0.1)

        # 2. Clear all registered singletons
        for singleton_dict in self._singletons_to_clear:
            try:
                logger.warning(
                    f"[STATE RESET] Clearing singleton: {type(singleton_dict).__name__}"
                )
                singleton_dict.clear()
            except Exception as e:
                logger.error(f"[STATE RESET] Failed to clear singleton: {e}")

        # 3. Force close all SQLite connections
        await self._close_all_sqlite_connections()

        # 4. Clear OpenAI client singleton
        await self._clear_openai_clients()

        # 5. Reset thread pool
        await self._reset_thread_pool()

        # 6. Call all registered callbacks
        for callback in self._reset_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"[STATE RESET] Callback failed: {e}")

        # 7. Force garbage collection
        logger.warning("[STATE RESET] Forcing garbage collection")
        gc.collect()
        gc.collect()  # Second pass to catch circular references
        gc.collect()  # Third pass for good measure

        # 8. Clear module-level caches
        self._clear_module_caches()

        logger.warning("[STATE RESET] State reset complete")

    async def _close_all_sqlite_connections(self):
        """Find and close all SQLite connections."""
        try:
            # Import here to avoid circular imports
            from ..session_cache import _instance as session_cache_instance
            from ..gemini_session_cache import _instance as gemini_cache_instance
            from ..grok_session_cache import _instance as grok_cache_instance

            # Close all cache instances
            caches = [
                ("session_cache", session_cache_instance),
                ("gemini_cache", gemini_cache_instance),
                ("grok_cache", grok_cache_instance),
            ]

            for name, cache in caches:
                if cache is not None:
                    logger.warning(f"[STATE RESET] Closing {name}")
                    try:
                        cache.close()
                    except Exception as e:
                        logger.error(f"[STATE RESET] Failed to close {name}: {e}")

            # Clear the singleton instances
            import sys

            if "mcp_second_brain.session_cache" in sys.modules:
                sys.modules["mcp_second_brain.session_cache"]._instance = None
            if "mcp_second_brain.gemini_session_cache" in sys.modules:
                sys.modules["mcp_second_brain.gemini_session_cache"]._instance = None
            if "mcp_second_brain.grok_session_cache" in sys.modules:
                sys.modules["mcp_second_brain.grok_session_cache"]._instance = None

        except Exception as e:
            logger.error(f"[STATE RESET] Failed to close SQLite connections: {e}")

    async def _clear_openai_clients(self):
        """Clear OpenAI client singleton."""
        try:
            from ..adapters.openai.client import OpenAIClientFactory

            # Clear all instances
            if hasattr(OpenAIClientFactory, "_instances"):
                logger.warning(
                    f"[STATE RESET] Clearing {len(OpenAIClientFactory._instances)} OpenAI client instances"
                )
                OpenAIClientFactory._instances.clear()

            # Also try to close any existing clients
            if hasattr(OpenAIClientFactory, "_instances"):
                for client in list(OpenAIClientFactory._instances.values()):
                    try:
                        if hasattr(client, "close"):
                            await client.close()
                        elif hasattr(client, "_client") and hasattr(
                            client._client, "close"
                        ):
                            await client._client.close()
                    except Exception as e:
                        logger.debug(
                            f"[STATE RESET] Failed to close OpenAI client: {e}"
                        )

        except Exception as e:
            logger.error(f"[STATE RESET] Failed to clear OpenAI clients: {e}")

    async def _reset_thread_pool(self):
        """Reset the shared thread pool."""
        try:
            from ..utils import thread_pool

            # Get current executor
            if (
                hasattr(thread_pool, "_shared_executor")
                and thread_pool._shared_executor
            ):
                logger.warning("[STATE RESET] Shutting down thread pool")
                executor = thread_pool._shared_executor
                thread_pool._shared_executor = None

                # Shutdown with short timeout
                executor.shutdown(wait=False)

        except Exception as e:
            logger.error(f"[STATE RESET] Failed to reset thread pool: {e}")

    def _clear_module_caches(self):
        """Clear various module-level caches."""
        # Clear functools caches
        try:
            import functools

            functools._lru_cache_clear_all = True  # Nonexistent, but shows intent

            # Clear any lru_cache decorated functions
            for module in list(sys.modules.values()):
                if module and hasattr(module, "__dict__"):
                    for attr_name, attr_value in module.__dict__.items():
                        if hasattr(attr_value, "cache_clear"):
                            try:
                                attr_value.cache_clear()
                                logger.debug(
                                    f"[STATE RESET] Cleared cache for {module.__name__}.{attr_name}"
                                )
                            except:
                                pass
        except Exception as e:
            logger.error(f"[STATE RESET] Failed to clear module caches: {e}")

    async def wrap_tool_execution(self, tool_func, *args, **kwargs):
        """Wrap a tool execution with state reset."""
        try:
            # Execute the tool
            result = await tool_func(*args, **kwargs)
            return result
        finally:
            # Always reset state after execution
            self._execution_count += 1
            logger.warning(
                f"[STATE RESET] Tool execution #{self._execution_count} complete, resetting state"
            )

            # Schedule reset as a background task so it doesn't block response
            asyncio.create_task(self._delayed_reset())

    async def _delayed_reset(self):
        """Delay reset slightly to allow response to be sent."""
        await asyncio.sleep(2.0)  # Give plenty of time for response to be sent
        await self.reset_all_state()


# Global instance
state_reset_manager = StateResetManager()
