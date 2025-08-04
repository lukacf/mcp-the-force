"""Simple SQLite-based content cache for deduplication."""

import sqlite3
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from .errors import CacheReadError, CacheWriteError, CacheTransactionError
from .retry import (
    retry_sqlite_operation,
    DEFAULT_RETRY_CONFIG,
    ATOMIC_OPERATION_RETRY_CONFIG,
    READ_OPERATION_RETRY_CONFIG,
)

logger = logging.getLogger(__name__)


class SimpleVectorStoreCache:
    """Simple content-addressable cache for vector stores.

    Provides two-level caching:
    1. File-level: content_hash -> file_id (for OpenAI file reuse)
    2. Store-level: fileset_hash -> store_id (for vector store reuse)
    """

    def __init__(self, db_path: str):
        """Initialize cache with SQLite database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()
        logger.info(f"Initialized SimpleVectorStoreCache: {db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get a properly configured SQLite connection."""
        conn = sqlite3.connect(self.db_path)
        # Apply concurrency settings to every connection
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_database(self):
        """Initialize database schema with proper concurrency settings."""
        with sqlite3.connect(self.db_path) as conn:
            # Configure SQLite for better concurrency
            conn.execute(
                "PRAGMA journal_mode=WAL"
            )  # Enable WAL mode for concurrent access
            conn.execute(
                "PRAGMA busy_timeout=30000"
            )  # 30 second timeout for lock contention
            conn.execute(
                "PRAGMA synchronous=NORMAL"
            )  # Balance between safety and performance

            # Create file cache table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_cache (
                    content_hash TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)

            # Create store cache table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS store_cache (
                    fileset_hash TEXT PRIMARY KEY,
                    store_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)

            # Create indexes
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_cache_created ON file_cache(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_store_cache_created ON store_cache(created_at)"
            )

    @retry_sqlite_operation(
        config=READ_OPERATION_RETRY_CONFIG,
        wrap_exception=CacheReadError,
        operation_description="Cache read operation",
    )
    def get_file_id(self, content_hash: str) -> Optional[str]:
        """Get cached file_id for content hash.

        Includes lightweight retry logic for transient database errors.

        Args:
            content_hash: SHA-256 hash of file content

        Returns:
            OpenAI file_id if cached, None otherwise

        Raises:
            CacheReadError: If database operation fails after retries
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT file_id FROM file_cache WHERE content_hash = ?",
                (content_hash,),
            )
            result = cursor.fetchone()
            return result[0] if result else None

    @retry_sqlite_operation(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Cache file operation",
    )
    def cache_file(self, content_hash: str, file_id: str) -> None:
        """Cache content_hash -> file_id mapping.

        Includes retry logic to handle transient SQLite errors during write operations.

        Args:
            content_hash: SHA-256 hash of file content
            file_id: OpenAI file identifier

        Raises:
            CacheWriteError: If database operation fails after retries
        """
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO file_cache (content_hash, file_id, created_at) VALUES (?, ?, ?)",
                (content_hash, file_id, int(time.time())),
            )

    @retry_sqlite_operation(
        config=READ_OPERATION_RETRY_CONFIG,
        wrap_exception=CacheReadError,
        operation_description="Cache store read operation",
    )
    def get_store_id(self, fileset_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached store for fileset hash.

        Includes lightweight retry logic for transient database errors.

        Args:
            fileset_hash: Hash of complete file set

        Returns:
            Dictionary with store_id and provider, or None if not found

        Raises:
            CacheReadError: If database operation fails after retries
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT store_id, provider FROM store_cache WHERE fileset_hash = ?",
                (fileset_hash,),
            )
            result = cursor.fetchone()
            if result:
                return {"store_id": result[0], "provider": result[1]}
            return None

    @retry_sqlite_operation(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Cache store operation",
    )
    def cache_store(self, fileset_hash: str, store_id: str, provider: str) -> None:
        """Cache fileset_hash -> store_id mapping.

        Includes retry logic to handle transient SQLite errors during write operations.

        Args:
            fileset_hash: Hash of complete file set
            store_id: Vector store identifier
            provider: Vector store provider (e.g., 'openai')

        Raises:
            CacheWriteError: If database operation fails after retries
        """
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO store_cache (fileset_hash, store_id, provider, created_at) VALUES (?, ?, ?, ?)",
                (fileset_hash, store_id, provider, int(time.time())),
            )

    @retry_sqlite_operation(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Cache cleanup operation",
    )
    def cleanup_old_entries(self, max_age_days: int = 30) -> None:
        """Clean up old cache entries.

        Includes retry logic to handle transient SQLite errors during cleanup operations.

        Args:
            max_age_days: Maximum age in days before cleanup

        Raises:
            CacheWriteError: If database operation fails after retries
        """
        cutoff_time = int(time.time()) - (max_age_days * 24 * 3600)

        with self._get_connection() as conn:
            cursor1 = conn.execute(
                "DELETE FROM file_cache WHERE created_at < ?", (cutoff_time,)
            )
            cursor2 = conn.execute(
                "DELETE FROM store_cache WHERE created_at < ?", (cutoff_time,)
            )

            logger.info(
                f"Cleaned up {cursor1.rowcount} files and {cursor2.rowcount} stores"
            )

    @retry_sqlite_operation(
        config=ATOMIC_OPERATION_RETRY_CONFIG,
        wrap_exception=CacheTransactionError,
        operation_description="Atomic cache or get operation",
    )
    def atomic_cache_or_get(
        self, content_hash: str, placeholder: str = "PENDING"
    ) -> tuple[Optional[str], bool]:
        """
        Atomically reserve a hash or retrieve an existing file_id.

        This method prevents race conditions by using an atomic INSERT OR IGNORE
        operation. Only one process can successfully insert a given content_hash,
        making that process responsible for uploading the file.

        This operation includes retry logic with exponential backoff to handle
        SQLite lock contention gracefully in high-concurrency scenarios.

        Args:
            content_hash: SHA-256 hash of file content
            placeholder: Placeholder value to indicate upload in progress

        Returns:
            Tuple of (file_id, we_are_uploader) where:
            - file_id: OpenAI file_id if already cached, None if upload needed,
                      or "PENDING" if another process is uploading
            - we_are_uploader: True if this process should perform the upload
        """
        now = int(time.time())
        with self._get_connection() as conn:
            # Use BEGIN IMMEDIATE to avoid write starvation under high concurrency
            conn.execute("BEGIN IMMEDIATE")

            try:
                # Attempt to atomically reserve this content hash
                cursor = conn.execute(
                    """
                    INSERT INTO file_cache (content_hash, file_id, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(content_hash) DO NOTHING
                    """,
                    (content_hash, placeholder, now),
                )

                we_are_uploader = cursor.rowcount == 1

                if not we_are_uploader:
                    # Another process already has this hash - fetch the current value
                    cursor = conn.execute(
                        "SELECT file_id FROM file_cache WHERE content_hash = ?",
                        (content_hash,),
                    )
                    result = cursor.fetchone()
                    file_id = result[0] if result else None
                    conn.commit()
                    return (file_id, False)

                # We successfully reserved this hash - we are the uploader
                conn.commit()
                return (None, True)

            except Exception:
                conn.rollback()
                raise

    @retry_sqlite_operation(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Cache finalization operation",
    )
    def finalize_file_id(self, content_hash: str, file_id: str) -> None:
        """
        Replace the placeholder with the real OpenAI file_id.

        This method safely updates the cached entry after a successful upload.
        It only updates entries that still have the PENDING placeholder,
        making it safe to call even if another process already finalized.

        Includes retry logic to handle transient SQLite errors during finalization.

        Args:
            content_hash: SHA-256 hash of file content
            file_id: OpenAI file identifier from successful upload
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE file_cache
                SET file_id = ?,
                    created_at = COALESCE(created_at, ?)
                WHERE content_hash = ? AND file_id = 'PENDING'
                """,
                (file_id, int(time.time()), content_hash),
            )

            if cursor.rowcount == 0:
                # Row was already finalized by another process, or hash doesn't exist
                logger.debug(f"File {content_hash} was already finalized or not found")
            else:
                logger.debug(f"Finalized cache entry for {content_hash} -> {file_id}")

    @retry_sqlite_operation(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Cache cleanup operation",
    )
    def cleanup_failed_upload(self, content_hash: str) -> None:
        """
        Clean up a failed upload by removing the PENDING placeholder.

        This allows another process to retry the upload later.
        Includes retry logic to handle transient SQLite errors during cleanup.

        Args:
            content_hash: SHA-256 hash of file content that failed to upload
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM file_cache WHERE content_hash = ? AND file_id = 'PENDING'",
                (content_hash,),
            )

            if cursor.rowcount > 0:
                logger.debug(f"Cleaned up failed upload placeholder for {content_hash}")

    @retry_sqlite_operation(
        config=DEFAULT_RETRY_CONFIG,
        wrap_exception=CacheWriteError,
        operation_description="Stale PENDING cleanup operation",
    )
    def cleanup_stale_pending_entries(self, max_age_minutes: int = 60) -> int:
        """Clean up stale PENDING entries that may have been left by crashed processes.

        This method removes PENDING entries that are older than the specified age,
        allowing future uploads of the same content to proceed. This addresses the
        issue where a process crash after reserving a hash but before finalizing
        would permanently block that content hash.

        Args:
            max_age_minutes: Maximum age in minutes for a PENDING entry before cleanup

        Returns:
            Number of stale entries cleaned up

        Raises:
            CacheWriteError: If database operation fails after retries
        """
        cutoff_time = int(time.time()) - (max_age_minutes * 60)

        with self._get_connection() as conn:
            cursor = conn.execute(
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

    @retry_sqlite_operation(
        config=READ_OPERATION_RETRY_CONFIG,
        wrap_exception=CacheReadError,
        operation_description="Cache statistics read operation",
    )
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Includes lightweight retry logic for transient database errors.

        Returns:
            Dictionary with cache statistics

        Raises:
            CacheReadError: If database operation fails after retries
        """
        with self._get_connection() as conn:
            cursor1 = conn.execute("SELECT COUNT(*) FROM file_cache")
            file_count = cursor1.fetchone()[0]

            cursor2 = conn.execute("SELECT COUNT(*) FROM store_cache")
            store_count = cursor2.fetchone()[0]

            # Count pending uploads
            cursor3 = conn.execute(
                "SELECT COUNT(*) FROM file_cache WHERE file_id = 'PENDING'"
            )
            pending_count = cursor3.fetchone()[0]

            return {
                "file_count": file_count,
                "store_count": store_count,
                "pending_uploads": pending_count,
                "cache_type": "SimpleVectorStoreCache",
            }


# Global cache instance
_cache: Optional[SimpleVectorStoreCache] = None


def get_cache() -> SimpleVectorStoreCache:
    """Get the project-specific cache instance."""
    global _cache
    if _cache is None:
        # Use project-local path instead of global user path to prevent data leakage
        cache_dir = Path(".mcp-the-force")
        cache_path = cache_dir / "vdb_cache.db"
        _cache = SimpleVectorStoreCache(str(cache_path))
    return _cache
