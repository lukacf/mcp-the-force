"""Cache-specific exception classes for proper error propagation."""


class CacheError(Exception):
    """Base exception for cache-related operations.

    This exception indicates a cache operation failed and upstream code
    should handle the failure appropriately (retry, fallback, etc.).
    """

    pass


class CacheWriteError(CacheError):
    """Raised when cache write operations fail.

    This includes operations like cache_file(), cache_store(),
    finalize_file_id(), and cleanup_failed_upload().

    Upstream code should handle this by either:
    - Retrying the operation (for transient failures)
    - Proceeding without caching (for persistent failures)
    - Logging the failure and continuing (degraded mode)
    """

    pass


class CacheReadError(CacheError):
    """Raised when cache read operations fail.

    This includes operations like get_file_id(), get_store_id(),
    and get_stats().

    Upstream code should handle this by:
    - Treating it as a cache miss (proceed without cached data)
    - Retrying the operation (for transient failures)
    - Logging the failure and using fallback behavior
    """

    pass


class CacheTransactionError(CacheError):
    """Raised when atomic cache operations fail.

    This is specifically for atomic_cache_or_get() which is critical
    for preventing race conditions in deduplication.

    Upstream code should handle this by:
    - Treating the file as if deduplication is disabled
    - Logging the failure and proceeding with upload
    - NOT interpreting as "another process is uploading"
    """

    pass
