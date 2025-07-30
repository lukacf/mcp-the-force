"""Cache for managing vector store lifecycles."""

import json
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
            vector_store_id TEXT PRIMARY KEY,
            name TEXT UNIQUE,
            session_id TEXT UNIQUE,
            provider TEXT NOT NULL CHECK(provider IN ('openai', 'inmemory', 'pinecone', 'hnsw')),
            provider_metadata TEXT,
            is_protected INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            expires_at INTEGER,
            updated_at INTEGER NOT NULL,
            document_count INTEGER DEFAULT 0,
            rollover_from TEXT REFERENCES vector_stores(vector_store_id),
            
            -- Ensure either name OR session_id is set, not both
            CHECK (
                (name IS NOT NULL AND session_id IS NULL) OR
                (name IS NULL AND session_id IS NOT NULL)
            )
        )
        """

        super().__init__(
            db_path=db_path,
            ttl=ttl,
            table_name="vector_stores",
            create_table_sql=create_table_sql,
            purge_probability=purge_probability,
        )

        # Create additional indexes for efficient queries
        if self._conn:
            with self._conn:
                # Index for session lookups
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_vs_session_id ON vector_stores(session_id)"
                )
                # Index for name lookups
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_vs_name ON vector_stores(name)"
                )
                # Index for expiration queries
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_vs_expires_at ON vector_stores(expires_at) "
                    "WHERE expires_at IS NOT NULL"
                )
                # Index for active named stores
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_vs_active_named ON vector_stores(name, is_active) "
                    "WHERE name IS NOT NULL"
                )
                # Index for rollover relationships
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_vs_rollover ON vector_stores(rollover_from) "
                    "WHERE rollover_from IS NOT NULL"
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

        # Check for existing active store (either non-expired or protected)
        current_time = int(time.time())
        rows = await self._execute_async(
            "SELECT vector_store_id FROM vector_stores "
            "WHERE session_id = ? AND is_active = 1 AND "
            "(expires_at IS NULL OR expires_at > ? OR is_protected = 1)",
            (session_id, current_time),
        )

        if rows and rows[0]:
            # Found existing store, renew its lease if it has one
            vector_store_id = rows[0][0]
            await self.renew_lease(session_id)
            logger.info(
                f"Reusing vector store {vector_store_id} for session {session_id}"
            )
            return vector_store_id, True

        # No existing store found
        return None, False

    async def get_store(
        self,
        session_id: Optional[str] = None,
        name: Optional[str] = None,
        vector_store_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get vector store information by session_id, name, or vector_store_id.

        Args:
            session_id: The session identifier
            name: The named store identifier
            vector_store_id: The vector store ID

        Returns:
            Dictionary with store information or None if not found
        """
        # Build query based on provided parameters
        conditions = []
        params = []

        if vector_store_id:
            conditions.append("vector_store_id = ?")
            params.append(vector_store_id)
        elif session_id:
            self._validate_session_id(session_id)
            conditions.append("session_id = ?")
            params.append(session_id)
        elif name:
            conditions.append("name = ?")
            params.append(name)
        else:
            raise ValueError(
                "At least one of session_id, name, or vector_store_id must be provided"
            )

        query = f"""
        SELECT vector_store_id, name, session_id, provider, provider_metadata,
               is_protected, is_active, created_at, expires_at, updated_at,
               document_count, rollover_from
        FROM vector_stores
        WHERE {' AND '.join(conditions)} AND is_active = 1
        """

        rows = await self._execute_async(query, tuple(params))

        if rows and rows[0]:
            row = rows[0]
            return {
                "vector_store_id": row[0],
                "name": row[1],
                "session_id": row[2],
                "provider": row[3],
                "provider_metadata": json.loads(row[4]) if row[4] else None,
                "is_protected": bool(row[5]),
                "is_active": bool(row[6]),
                "created_at": row[7],
                "expires_at": row[8],
                "updated_at": row[9],
                "document_count": row[10],
                "rollover_from": row[11],
            }

        return None

    async def register_store(
        self,
        vector_store_id: str,
        provider: str,
        session_id: Optional[str] = None,
        name: Optional[str] = None,
        protected: bool = False,
        ttl_seconds: Optional[int] = None,
        provider_metadata: Optional[Dict[str, Any]] = None,
        rollover_from: Optional[str] = None,
    ) -> None:
        """Register a newly created vector store.

        Args:
            vector_store_id: The created vector store ID
            provider: The vector store provider
            session_id: The session identifier (optional, mutually exclusive with name)
            name: The named store identifier (optional, mutually exclusive with session_id)
            protected: Whether this store should be protected from cleanup
            ttl_seconds: Optional custom TTL in seconds (only applies to session stores)
            provider_metadata: Optional provider-specific metadata
            rollover_from: Optional ID of previous store this rolled over from
        """
        # Validate that either session_id OR name is provided, not both
        if (session_id is None and name is None) or (
            session_id is not None and name is not None
        ):
            raise ValueError("Exactly one of session_id or name must be provided")

        if session_id:
            self._validate_session_id(session_id)

        current_time = int(time.time())

        # Calculate expiration time
        if session_id and ttl_seconds is not None:
            expires_at = current_time + ttl_seconds
        elif session_id:
            expires_at = current_time + self.ttl
        else:
            # Named stores don't expire by default
            expires_at = None

        # Serialize provider metadata if provided
        metadata_json = json.dumps(provider_metadata) if provider_metadata else None

        # Insert or replace the entry
        await self._execute_async(
            "INSERT OR REPLACE INTO vector_stores "
            "(vector_store_id, name, session_id, provider, provider_metadata, "
            "is_protected, is_active, created_at, expires_at, updated_at, "
            "document_count, rollover_from) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                vector_store_id,
                name,
                session_id,
                provider,
                metadata_json,
                int(protected),
                1,  # is_active
                current_time,
                expires_at,
                current_time,
                0,  # document_count
                rollover_from,
            ),
            fetch=False,
        )

        identifier = f"session {session_id}" if session_id else f"name '{name}'"
        logger.info(
            f"Registered {'protected ' if protected else ''}vector store "
            f"{vector_store_id} for {identifier}"
            f"{f' with TTL {ttl_seconds or self.ttl}s' if expires_at else ''}"
        )

        # Probabilistic cleanup
        await self._probabilistic_cleanup()

    async def set_inactive(self, vector_store_id: str) -> bool:
        """Mark a store as inactive (for memory rollover).

        Args:
            vector_store_id: The vector store ID to mark as inactive

        Returns:
            True if successfully marked inactive, False if not found
        """
        current_time = int(time.time())

        await self._execute_async(
            "UPDATE vector_stores SET is_active = 0, updated_at = ? WHERE vector_store_id = ?",
            (current_time, vector_store_id),
            fetch=False,
        )

        # Check if any rows were updated
        rows = await self._execute_async("SELECT changes() AS count", ())

        updated = rows[0][0] > 0 if rows else False
        if updated:
            logger.info(f"Marked vector store {vector_store_id} as inactive")

        return bool(updated)

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
            "SELECT vector_store_id, name, session_id, provider "
            "FROM vector_stores "
            "WHERE expires_at IS NOT NULL AND expires_at < ? "
            "AND is_protected = 0 AND is_active = 1 "
            "ORDER BY expires_at "
            "LIMIT ?",
            (current_time, limit),
        )

        return (
            [
                {
                    "vector_store_id": row[0],
                    "name": row[1],
                    "session_id": row[2],
                    "provider": row[3],
                }
                for row in rows
            ]
            if rows
            else []
        )

    async def remove_store(self, vector_store_id: str) -> bool:
        """Remove a vector store entry after successful cleanup.

        Args:
            vector_store_id: The vector store ID to remove

        Returns:
            True if removed, False if not found
        """
        await self._execute_async(
            "DELETE FROM vector_stores WHERE vector_store_id = ?",
            (vector_store_id,),
            fetch=False,
        )

        # Check if any rows were deleted
        rows = await self._execute_async("SELECT changes() AS count", ())

        deleted = rows[0][0] > 0 if rows else False
        if deleted:
            logger.debug(f"Removed vector store entry {vector_store_id}")

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
            "SELECT COUNT(*) FROM vector_stores WHERE is_active = 1", ()
        )

        expired_rows = await self._execute_async(
            "SELECT COUNT(*) FROM vector_stores WHERE expires_at IS NOT NULL "
            "AND expires_at <= ? AND is_protected = 0 AND is_active = 1",
            (current_time,),
        )

        protected_rows = await self._execute_async(
            "SELECT COUNT(*) FROM vector_stores WHERE is_protected = 1", ()
        )

        named_rows = await self._execute_async(
            "SELECT COUNT(*) FROM vector_stores WHERE name IS NOT NULL", ()
        )

        session_rows = await self._execute_async(
            "SELECT COUNT(*) FROM vector_stores WHERE session_id IS NOT NULL", ()
        )

        return {
            "total": total_rows[0][0] if total_rows else 0,
            "active": active_rows[0][0] if active_rows else 0,
            "expired": expired_rows[0][0] if expired_rows else 0,
            "protected": protected_rows[0][0] if protected_rows else 0,
            "named": named_rows[0][0] if named_rows else 0,
            "session": session_rows[0][0] if session_rows else 0,
        }
