"""Cache for managing vector store lifecycles."""

import time
import logging
from typing import Optional, List, Tuple, Dict, Any
from .sqlite_base_cache import BaseSQLiteCache

logger = logging.getLogger(__name__)


class VectorStoreCache(BaseSQLiteCache):
    """Manages vector store lifecycle with TTL and cleanup."""

    def __init__(self, db_path: str, ttl: int = 7200, purge_probability: float = 0.02):
        """Initialize the vector store cache.

        Args:
            db_path: Path to the SQLite database file
            ttl: Time-to-live for vector stores in seconds (default: 2 hours)
            purge_probability: Probability of running cleanup on operations (default: 2%)
        """
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS vector_stores (
            session_id TEXT PRIMARY KEY,
            vector_store_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            protected INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """

        super().__init__(
            db_path=db_path,
            ttl=ttl,
            table_name="vector_stores",
            create_table_sql=create_table_sql,
            purge_probability=purge_probability,
        )

        # Create additional index for expiration queries
        if self._conn:
            with self._conn:
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_vector_stores_expires "
                    "ON vector_stores(expires_at)"
                )

    async def get_or_create_placeholder(
        self, session_id: str, provider: str = "openai", protected: bool = False
    ) -> Tuple[Optional[str], bool]:
        """Get existing vector store or create a placeholder entry.

        This method only manages the cache entry. The actual vector store
        creation is handled by the VectorStoreManager.

        Args:
            session_id: The session identifier
            provider: The vector store provider (default: "openai")
            protected: Whether this store should be protected from cleanup

        Returns:
            Tuple of (vector_store_id if exists, was_reused)
        """
        self._validate_session_id(session_id)

        # Check for existing non-expired store
        current_time = int(time.time())
        rows = await self._execute_async(
            "SELECT vector_store_id FROM vector_stores "
            "WHERE session_id = ? AND expires_at > ?",
            (session_id, current_time),
        )

        if rows and rows[0]:
            # Found existing store, renew its lease
            vector_store_id = rows[0][0]
            await self.renew_lease(session_id)
            logger.info(
                f"Reusing vector store {vector_store_id} for session {session_id}"
            )
            return vector_store_id, True

        # No existing store found
        return None, False

    async def register_store(
        self,
        session_id: str,
        vector_store_id: str,
        provider: str = "openai",
        protected: bool = False,
    ) -> None:
        """Register a newly created vector store.

        Args:
            session_id: The session identifier
            vector_store_id: The created vector store ID
            provider: The vector store provider
            protected: Whether this store should be protected from cleanup
        """
        self._validate_session_id(session_id)

        current_time = int(time.time())
        expires_at = current_time + self.ttl

        # Insert or replace the entry
        await self._execute_async(
            "INSERT OR REPLACE INTO vector_stores "
            "(session_id, vector_store_id, provider, expires_at, protected, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                vector_store_id,
                provider,
                expires_at,
                int(protected),
                current_time,
                current_time,
            ),
            fetch=False,
        )

        logger.info(
            f"Registered {'protected ' if protected else ''}vector store "
            f"{vector_store_id} for session {session_id} with TTL {self.ttl}s"
        )

        # Probabilistic cleanup
        await self._probabilistic_cleanup()

    async def renew_lease(self, session_id: str) -> bool:
        """Extend the TTL for a vector store.

        Args:
            session_id: The session identifier

        Returns:
            True if lease was renewed, False if not found
        """
        self._validate_session_id(session_id)

        current_time = int(time.time())
        new_expires_at = current_time + self.ttl

        # Update expiration time and updated_at
        await self._execute_async(
            "UPDATE vector_stores SET expires_at = ?, updated_at = ? WHERE session_id = ?",
            (new_expires_at, current_time, session_id),
            fetch=False,
        )

        # Check if any rows were updated
        rows = await self._execute_async("SELECT changes() AS count", ())

        updated = rows[0][0] > 0 if rows else False
        if updated:
            logger.debug(f"Renewed lease for session {session_id}")

        return bool(updated)

    async def get_expired_stores(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get expired vector stores for cleanup.

        Args:
            limit: Maximum number of stores to return

        Returns:
            List of expired store records
        """
        current_time = int(time.time())

        rows = await self._execute_async(
            "SELECT session_id, vector_store_id, provider "
            "FROM vector_stores "
            "WHERE expires_at < ? AND protected = 0 "
            "ORDER BY expires_at "
            "LIMIT ?",
            (current_time, limit),
        )

        return (
            [
                {"session_id": row[0], "vector_store_id": row[1], "provider": row[2]}
                for row in rows
            ]
            if rows
            else []
        )

    async def remove_store(self, session_id: str) -> bool:
        """Remove a vector store entry after successful cleanup.

        Args:
            session_id: The session identifier

        Returns:
            True if removed, False if not found
        """
        self._validate_session_id(session_id)

        await self._execute_async(
            "DELETE FROM vector_stores WHERE session_id = ?", (session_id,), fetch=False
        )

        # Check if any rows were deleted
        rows = await self._execute_async("SELECT changes() AS count", ())

        deleted = rows[0][0] > 0 if rows else False
        if deleted:
            logger.debug(f"Removed vector store entry for session {session_id}")

        return bool(deleted)

    async def cleanup_orphaned(self) -> int:
        """Remove entries older than 30 days regardless of expiration.

        This catches any stores that somehow weren't cleaned up properly.

        Returns:
            Number of entries removed
        """
        cutoff = int(time.time()) - (30 * 24 * 60 * 60)  # 30 days

        await self._execute_async(
            "DELETE FROM vector_stores WHERE created_at < ?", (cutoff,), fetch=False
        )

        # Get count of deleted rows
        rows = await self._execute_async("SELECT changes() AS count", ())

        count = rows[0][0] if rows else 0
        if count > 0:
            logger.info(f"Cleaned up {count} orphaned vector store entries")

        return int(count)

    async def get_stats(self) -> Dict[str, int]:
        """Get statistics about the vector store cache.

        Returns:
            Dictionary with counts of different store states
        """
        current_time = int(time.time())

        # Get various counts
        total_rows = await self._execute_async("SELECT COUNT(*) FROM vector_stores", ())

        active_rows = await self._execute_async(
            "SELECT COUNT(*) FROM vector_stores WHERE expires_at > ?", (current_time,)
        )

        expired_rows = await self._execute_async(
            "SELECT COUNT(*) FROM vector_stores WHERE expires_at <= ? AND protected = 0",
            (current_time,),
        )

        protected_rows = await self._execute_async(
            "SELECT COUNT(*) FROM vector_stores WHERE protected = 1", ()
        )

        return {
            "total": total_rows[0][0] if total_rows else 0,
            "active": active_rows[0][0] if active_rows else 0,
            "expired": expired_rows[0][0] if expired_rows else 0,
            "protected": protected_rows[0][0] if protected_rows else 0,
        }
