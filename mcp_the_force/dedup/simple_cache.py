"""Simple SQLite-based content cache for deduplication."""

import time
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, cast

from ..sqlite_base_cache import BaseSQLiteCache
from ..utils.thread_pool import run_in_thread_pool
from .errors import CacheReadError, CacheWriteError, CacheTransactionError
from .retry import (
    retry_sqlite_operation_async,
    DEFAULT_RETRY_CONFIG,
    ATOMIC_OPERATION_RETRY_CONFIG,
    READ_OPERATION_RETRY_CONFIG,
)

logger = logging.getLogger(__name__)


class DeduplicationCache(BaseSQLiteCache):
    """Simple content-addressable cache for vector stores.

    Provides two-level caching:
    1. File-level: content_hash -> file_id (for OpenAI file reuse)
    2. Store-level: fileset_hash -> store_id (for vector store reuse)

    Uses BaseSQLiteCache for consistent SQLite patterns across the codebase.
    """

    def __init__(self, db_path: str, ttl: int = 2592000):  # 30 days default TTL
        """Initialize cache with SQLite database.

        Args:
            db_path: Path to SQLite database file
            ttl: Time-to-live for cache entries in seconds (default: 30 days)
        """
        # Define the table creation SQL for both tables
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS file_cache (
            content_hash TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
        )
        """

        # Set up a cross-process file lock (best-effort; falls back to no-op on platforms
        # without fcntl). This prevents rare races when multiple processes try to reserve
        # the same hash at the exact same time (seen in CI).
        self._fcntl = None
        self._file_lock_handle = None
        lock_path = Path(db_path).with_suffix(Path(db_path).suffix + ".lock")
        try:
            import fcntl  # type: ignore

            lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_lock_handle = open(lock_path, "a+")
            self._fcntl = fcntl
        except Exception:
            # On Windows or if anything goes wrong, just skip file locking; we still
            # have SQLite constraints and busy timeouts as a safety net.
            self._fcntl = None
            self._file_lock_handle = None

        super().__init__(
            db_path=db_path,
            ttl=ttl,
            table_name="file_cache",
            create_table_sql=create_table_sql,
            purge_probability=0.01,
        )

        # Create the store_cache table and indexes
        self._create_additional_tables()
        logger.info(f"Initialized DeduplicationCache: {db_path}")

    @contextmanager
    def _process_lock(self):
        """A cross-process mutex using fcntl-based file lock (best effort)."""
        if self._fcntl and self._file_lock_handle:
            self._fcntl.flock(self._file_lock_handle.fileno(), self._fcntl.LOCK_EX)
            try:
                yield
            finally:
                self._fcntl.flock(self._file_lock_handle.fileno(), self._fcntl.LOCK_UN)
        else:
            yield

    def _create_additional_tables(self):
        """Create additional tables and indexes for deduplication cache."""
        if self._conn is None:
            raise RuntimeError("Database connection is not initialized")

        with self._conn:
            # Create store cache table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS store_cache (
                    fileset_hash TEXT PRIMARY KEY,
                    store_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
                )
            """)

            # Create embedding cache table for HNSW deduplication
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    content_hash TEXT PRIMARY KEY,
                    embedding BLOB NOT NULL,
                    dimensions INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
                )
            """)

            # Create indexes for better performance
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_cache_created ON file_cache(created_at)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_store_cache_created ON store_cache(created_at)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_store_cache_updated ON store_cache(updated_at)"
            )

    @retry_sqlite_operation_async(
        config=READ_OPERATION_RETRY_CONFIG,
        wrap_exception=CacheReadError,
        operation_description="Cache read operation",
    )
    async def get_file_id(self, content_hash: str) -> Optional[str]:
        """Get cached file_id for content hash.

        Args:
            content_hash: SHA-256 hash of file content

        Returns:
            OpenAI file_id if cached, None otherwise

        Raises:
            CacheReadError: If database operation fails after retries
        """
        rows = await self._execute_async(
            "SELECT file_id FROM file_cache WHERE content_hash = ?",
            (content_hash,),
        )
        return rows[0][0] if rows and rows[0] else None

    @retry_sqlite_operation_async(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Cache file operation",
    )
    async def cache_file(self, content_hash: str, file_id: str) -> None:
        """Cache content_hash -> file_id mapping.

        Args:
            content_hash: SHA-256 hash of file content
            file_id: OpenAI file identifier

        Raises:
            CacheWriteError: If database operation fails after retries
        """
        current_time = int(time.time())
        await self._execute_async(
            "INSERT OR IGNORE INTO file_cache (content_hash, file_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (content_hash, file_id, current_time, current_time),
            fetch=False,
        )

    @retry_sqlite_operation_async(
        config=READ_OPERATION_RETRY_CONFIG,
        wrap_exception=CacheReadError,
        operation_description="Cache store read operation",
    )
    async def get_store_id(self, fileset_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached store for fileset hash.

        Args:
            fileset_hash: Hash of complete file set

        Returns:
            Dictionary with store_id and provider, or None if not found

        Raises:
            CacheReadError: If database operation fails after retries
        """
        rows = await self._execute_async(
            "SELECT store_id, provider FROM store_cache WHERE fileset_hash = ?",
            (fileset_hash,),
        )
        if rows and rows[0]:
            return {"store_id": rows[0][0], "provider": rows[0][1]}
        return None

    @retry_sqlite_operation_async(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Cache store operation",
    )
    async def cache_store(
        self, fileset_hash: str, store_id: str, provider: str
    ) -> None:
        """Cache fileset_hash -> store_id mapping.

        Args:
            fileset_hash: Hash of complete file set
            store_id: Vector store identifier
            provider: Vector store provider (e.g., 'openai')

        Raises:
            CacheWriteError: If database operation fails after retries
        """
        current_time = int(time.time())
        await self._execute_async(
            "INSERT OR IGNORE INTO store_cache (fileset_hash, store_id, provider, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (fileset_hash, store_id, provider, current_time, current_time),
            fetch=False,
        )

    @retry_sqlite_operation_async(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Cache cleanup operation",
    )
    async def cleanup_old_entries(self, max_age_days: int = 30) -> None:
        """Clean up old cache entries.

        Args:
            max_age_days: Maximum age in days before cleanup

        Raises:
            CacheWriteError: If database operation fails after retries
        """
        cutoff_time = int(time.time()) - (max_age_days * 24 * 3600)

        # Use a synchronous function to execute multiple statements atomically
        def _sync_cleanup():
            if self._conn is None:
                raise RuntimeError("Database connection is closed")

            with self._lock, self._conn:
                cursor1 = self._conn.execute(
                    "DELETE FROM file_cache WHERE created_at < ?", (cutoff_time,)
                )
                cursor2 = self._conn.execute(
                    "DELETE FROM store_cache WHERE created_at < ?", (cutoff_time,)
                )

                logger.info(
                    f"Cleaned up {cursor1.rowcount} files and {cursor2.rowcount} stores"
                )
                return cursor1.rowcount, cursor2.rowcount

        await run_in_thread_pool(_sync_cleanup)

    @retry_sqlite_operation_async(
        config=ATOMIC_OPERATION_RETRY_CONFIG,
        wrap_exception=CacheTransactionError,
        operation_description="Atomic cache or get operation",
    )
    async def atomic_cache_or_get(
        self, content_hash: str, placeholder: str = "PENDING"
    ) -> Tuple[Optional[str], bool]:
        """
        Atomically reserve a hash or retrieve an existing file_id.

        This method prevents race conditions by using an atomic INSERT OR IGNORE
        operation. Only one process can successfully insert a given content_hash,
        making that process responsible for uploading the file.

        Args:
            content_hash: SHA-256 hash of file content
            placeholder: Placeholder value to indicate upload in progress

        Returns:
            Tuple of (file_id, we_are_uploader) where:
            - file_id: OpenAI file_id if already cached, None if upload needed,
                      or "PENDING" if another process is uploading
            - we_are_uploader: True if this process should perform the upload
        """

        def _sync_atomic_op():
            if self._conn is None:
                raise RuntimeError("Database connection is closed")

            now = int(time.time())
            with self._process_lock():  # cross-process mutex
                with self._lock, self._conn:
                    # Use EXCLUSIVE to guarantee only one writer across processes.
                    self._conn.execute("BEGIN EXCLUSIVE")

                    try:
                        # Attempt to atomically reserve this content hash. Using RETURNING avoids
                        # rowcount ambiguity on some SQLite builds.
                        cursor = self._conn.execute(
                            """
                            INSERT INTO file_cache (content_hash, file_id, created_at, updated_at)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(content_hash) DO NOTHING
                            RETURNING content_hash
                            """,
                            (content_hash, placeholder, now, now),
                        )

                        row = cursor.fetchone()
                        we_are_uploader = row is not None

                        if not we_are_uploader:
                            # Another process already has this hash - fetch the current value
                            cursor = self._conn.execute(
                                "SELECT file_id FROM file_cache WHERE content_hash = ?",
                                (content_hash,),
                            )
                            result = cursor.fetchone()
                            file_id = result[0] if result else None
                            self._conn.commit()
                            return (file_id, False)

                        # We successfully reserved this hash - we are the uploader
                        self._conn.commit()
                        return (None, True)

                    except Exception:
                        self._conn.rollback()
                        raise

        result = await run_in_thread_pool(_sync_atomic_op)
        return cast(Tuple[Optional[str], bool], result)

    @retry_sqlite_operation_async(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Cache finalization operation",
    )
    async def finalize_file_id(self, content_hash: str, file_id: str) -> None:
        """
        Replace the placeholder with the real OpenAI file_id.

        This method safely updates the cached entry after a successful upload.
        It only updates entries that still have the PENDING placeholder,
        making it safe to call even if another process already finalized.

        Args:
            content_hash: SHA-256 hash of file content
            file_id: OpenAI file identifier from successful upload
        """

        def _sync_finalize():
            if self._conn is None:
                raise RuntimeError("Database connection is closed")

            with self._lock, self._conn:
                cursor = self._conn.execute(
                    """
                    UPDATE file_cache
                    SET file_id = ?,
                        updated_at = COALESCE(created_at, ?)
                    WHERE content_hash = ? AND file_id = 'PENDING'
                    """,
                    (file_id, int(time.time()), content_hash),
                )

                if cursor.rowcount == 0:
                    # Row was already finalized by another process, or hash doesn't exist
                    logger.debug(
                        f"File {content_hash} was already finalized or not found"
                    )
                else:
                    logger.debug(
                        f"Finalized cache entry for {content_hash} -> {file_id}"
                    )

                return cursor.rowcount

        await run_in_thread_pool(_sync_finalize)

    @retry_sqlite_operation_async(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Cache cleanup operation",
    )
    async def cleanup_failed_upload(self, content_hash: str) -> None:
        """
        Clean up a failed upload by removing the PENDING placeholder.

        This allows another process to retry the upload later.

        Args:
            content_hash: SHA-256 hash of file content that failed to upload
        """

        def _sync_cleanup_failed():
            if self._conn is None:
                raise RuntimeError("Database connection is closed")

            with self._lock, self._conn:
                cursor = self._conn.execute(
                    "DELETE FROM file_cache WHERE content_hash = ? AND file_id = 'PENDING'",
                    (content_hash,),
                )

                if cursor.rowcount > 0:
                    logger.debug(
                        f"Cleaned up failed upload placeholder for {content_hash}"
                    )

                return cursor.rowcount

        await run_in_thread_pool(_sync_cleanup_failed)

    @retry_sqlite_operation_async(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Stale PENDING cleanup operation",
    )
    async def cleanup_stale_pending_entries(self, max_age_minutes: int = 60) -> int:
        """Clean up stale PENDING entries that may have been left by crashed processes.

        Args:
            max_age_minutes: Maximum age in minutes for a PENDING entry before cleanup

        Returns:
            Number of stale entries cleaned up

        Raises:
            CacheWriteError: If database operation fails after retries
        """

        def _sync_cleanup_stale():
            if self._conn is None:
                raise RuntimeError("Database connection is closed")

            cutoff_time = int(time.time()) - (max_age_minutes * 60)

            with self._lock, self._conn:
                cursor = self._conn.execute(
                    "DELETE FROM file_cache WHERE file_id = 'PENDING' AND created_at < ?",
                    (cutoff_time,),
                )

                cleanup_count = cursor.rowcount
                if cleanup_count > 0:
                    logger.info(
                        f"Cleaned up {cleanup_count} stale PENDING entries older than {max_age_minutes} minutes"
                    )
                else:
                    logger.debug(
                        f"No stale PENDING entries found (older than {max_age_minutes} minutes)"
                    )

                return cleanup_count

        result = await run_in_thread_pool(_sync_cleanup_stale)
        return cast(int, result)

    @retry_sqlite_operation_async(
        config=READ_OPERATION_RETRY_CONFIG,
        wrap_exception=CacheReadError,
        operation_description="Cache statistics read operation",
    )
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics

        Raises:
            CacheReadError: If database operation fails after retries
        """

        def _sync_get_stats():
            if self._conn is None:
                raise RuntimeError("Database connection is closed")

            with self._lock, self._conn:
                cursor1 = self._conn.execute("SELECT COUNT(*) FROM file_cache")
                file_count = cursor1.fetchone()[0]

                cursor2 = self._conn.execute("SELECT COUNT(*) FROM store_cache")
                store_count = cursor2.fetchone()[0]

                # Count pending uploads
                cursor3 = self._conn.execute(
                    "SELECT COUNT(*) FROM file_cache WHERE file_id = 'PENDING'"
                )
                pending_count = cursor3.fetchone()[0]

                return {
                    "file_count": file_count,
                    "store_count": store_count,
                    "pending_uploads": pending_count,
                    "cache_type": "DeduplicationCache",
                }

        result = await run_in_thread_pool(_sync_get_stats)
        return cast(Dict[str, Any], result)

    @retry_sqlite_operation_async(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Store references cleanup",
    )
    async def remove_store_references(self, store_id: str) -> int:
        """Remove all deduplication cache entries referencing a deleted store.

        Args:
            store_id: Vector store ID to remove references for

        Returns:
            Number of cache entries removed
        """

        def _sync_remove_store_refs():
            if self._conn is None:
                raise RuntimeError("Database connection is closed")

            with self._lock, self._conn:
                cursor = self._conn.execute(
                    "DELETE FROM store_cache WHERE store_id = ?", (store_id,)
                )
                return cursor.rowcount

        result = await run_in_thread_pool(_sync_remove_store_refs)
        return cast(int, result)


# Legacy alias removed - use DeduplicationCache directly for clarity

# Path-keyed cache instances for proper isolation
_cache_instances: Dict[str, DeduplicationCache] = {}


def get_cache(cache_path: Optional[str] = None) -> DeduplicationCache:
    """Get the project-specific cache instance.

    Args:
        cache_path: Optional explicit cache path. If None, uses project default.

    Returns:
        Cache instance for the specified path
    """
    if cache_path is None:
        # Use project-local path instead of global user path to prevent data leakage
        cache_dir = Path(".mcp-the-force")
        cache_path = str(cache_dir / "vdb_cache.db")

    # Use path-keyed dictionary for proper isolation
    if cache_path not in _cache_instances:
        _cache_instances[cache_path] = DeduplicationCache(cache_path)

    return _cache_instances[cache_path]
