"""Simple SQLite-based content cache for deduplication."""

import sqlite3
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

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

    def get_file_id(self, content_hash: str) -> Optional[str]:
        """Get cached file_id for content hash.

        Args:
            content_hash: SHA-256 hash of file content

        Returns:
            OpenAI file_id if cached, None otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT file_id FROM file_cache WHERE content_hash = ?",
                    (content_hash,),
                )
                result = cursor.fetchone()
                return result[0] if result else None

        except sqlite3.Error as e:
            logger.error(f"Error retrieving file_id for hash {content_hash}: {e}")
            return None

    def cache_file(self, content_hash: str, file_id: str) -> None:
        """Cache content_hash -> file_id mapping.

        Args:
            content_hash: SHA-256 hash of file content
            file_id: OpenAI file identifier
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO file_cache (content_hash, file_id, created_at) VALUES (?, ?, ?)",
                    (content_hash, file_id, int(time.time())),
                )
        except sqlite3.Error as e:
            logger.error(f"Error caching file {content_hash}: {e}")

    def get_store_id(self, fileset_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached store for fileset hash.

        Args:
            fileset_hash: Hash of complete file set

        Returns:
            Dictionary with store_id and provider, or None if not found
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT store_id, provider FROM store_cache WHERE fileset_hash = ?",
                    (fileset_hash,),
                )
                result = cursor.fetchone()
                if result:
                    return {"store_id": result[0], "provider": result[1]}
                return None

        except sqlite3.Error as e:
            logger.error(f"Error retrieving store for hash {fileset_hash}: {e}")
            return None

    def cache_store(self, fileset_hash: str, store_id: str, provider: str) -> None:
        """Cache fileset_hash -> store_id mapping.

        Args:
            fileset_hash: Hash of complete file set
            store_id: Vector store identifier
            provider: Vector store provider (e.g., 'openai')
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO store_cache (fileset_hash, store_id, provider, created_at) VALUES (?, ?, ?, ?)",
                    (fileset_hash, store_id, provider, int(time.time())),
                )
        except sqlite3.Error as e:
            logger.error(f"Error caching store {fileset_hash}: {e}")

    def cleanup_old_entries(self, max_age_days: int = 30) -> None:
        """Clean up old cache entries.

        Args:
            max_age_days: Maximum age in days before cleanup
        """
        cutoff_time = int(time.time()) - (max_age_days * 24 * 3600)

        try:
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

        except sqlite3.Error as e:
            logger.error(f"Error during cleanup: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            with self._get_connection() as conn:
                cursor1 = conn.execute("SELECT COUNT(*) FROM file_cache")
                file_count = cursor1.fetchone()[0]

                cursor2 = conn.execute("SELECT COUNT(*) FROM store_cache")
                store_count = cursor2.fetchone()[0]

                return {
                    "file_count": file_count,
                    "store_count": store_count,
                    "cache_type": "SimpleVectorStoreCache",
                }

        except sqlite3.Error as e:
            logger.error(f"Error getting stats: {e}")
            return {
                "file_count": 0,
                "store_count": 0,
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
