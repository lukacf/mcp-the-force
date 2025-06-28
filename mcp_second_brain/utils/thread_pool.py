"""Shared thread pool for async operations."""

import asyncio
import threading
import atexit
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from ..config import get_settings

# Thread-safe singleton implementation
_shared_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def get_shared_executor(max_workers: Optional[int] = None) -> ThreadPoolExecutor:
    """Get the shared thread pool instance.

    Uses double-checked locking pattern for thread safety.
    """
    global _shared_executor

    if _shared_executor is None:
        with _executor_lock:
            if _shared_executor is None:
                if max_workers is None:
                    settings = get_settings()
                    max_workers = settings.mcp.thread_pool_workers
                _shared_executor = ThreadPoolExecutor(
                    max_workers=max_workers, thread_name_prefix="mcp-worker"
                )
                # Register cleanup
                atexit.register(_shared_executor.shutdown, wait=True)

    return _shared_executor


async def run_in_thread_pool(func, *args, **kwargs):
    """Run a function in the shared thread pool.

    Args:
        func: The function to run
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function

    Returns:
        The result of the function call
    """
    loop = asyncio.get_event_loop()
    executor = get_shared_executor()
    return await loop.run_in_executor(executor, func, *args, **kwargs)
