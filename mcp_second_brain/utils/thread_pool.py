from concurrent.futures import ThreadPoolExecutor
from typing import Optional

_shared_executor: Optional[ThreadPoolExecutor] = None


def get_shared_executor(max_workers: int = 20) -> ThreadPoolExecutor:
    """Return a shared thread pool executor."""
    global _shared_executor
    if _shared_executor is None:
        _shared_executor = ThreadPoolExecutor(max_workers=max_workers)
    return _shared_executor
