"""SQLite-based deduplication for search results that persists across sessions."""

import sqlite3
import time
from typing import Dict, Any, List, Tuple
from pathlib import Path
import logging

from ..dedup.hashing import compute_content_hash

logger = logging.getLogger(__name__)


class SQLiteSearchDeduplicator:
    """Manages deduplication for search results using SQLite for persistence."""

    def __init__(self, db_path: Path, ttl_hours: int = 24):
        """Initialize deduplicator with SQLite database.

        Args:
            db_path: Path to SQLite database
            ttl_hours: Time-to-live for cache entries in hours (default: 24)
        """
        self.db_path = db_path
        self.ttl_seconds = ttl_hours * 3600
        self._init_database()

    def _init_database(self):
        """Initialize the deduplication tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_dedup_cache (
                    session_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    query TEXT,
                    PRIMARY KEY (session_id, content_hash)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dedup_timestamp 
                ON search_dedup_cache(timestamp)
            """)
            conn.commit()

    @staticmethod
    def compute_content_hash_for_dedup(content: str, file_id: str = "") -> str:
        """Compute a hash for deduplication based on content and file_id.

        Uses the centralized hashing function that normalizes line endings
        for cross-platform consistency.
        """
        # Include both content and file_id to handle same content from different files
        combined = f"{content}:{file_id}"
        # Use the centralized hashing function that normalizes line endings
        return compute_content_hash(combined)[:16]

    def _cleanup_expired(self, conn: sqlite3.Connection):
        """Remove expired cache entries."""
        expiry_time = int(time.time()) - self.ttl_seconds
        conn.execute(
            "DELETE FROM search_dedup_cache WHERE timestamp < ?", (expiry_time,)
        )

    def clear_session_cache(self, session_id: str):
        """Clear the deduplication cache for a specific session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM search_dedup_cache WHERE session_id = ?", (session_id,)
            )
            conn.commit()
        logger.info(f"[DEDUP] Cleared cache for session {session_id}")

    def deduplicate_results(
        self,
        all_results: List[Dict[str, Any]],
        max_results: int,
        session_id: str = "default",
        query: str = "",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Deduplicate search results based on content hash.

        Args:
            all_results: List of search results to deduplicate
            max_results: Maximum number of results to return
            session_id: Session identifier for scoping deduplication
            query: The search query (for logging/debugging)

        Returns:
            Tuple of (deduplicated_results, duplicate_count)
        """
        deduplicated_results = []
        duplicate_count = 0
        current_time = int(time.time())

        with sqlite3.connect(self.db_path) as conn:
            # Clean up expired entries first
            self._cleanup_expired(conn)

            # Get existing hashes for this session
            cursor = conn.execute(
                "SELECT content_hash FROM search_dedup_cache WHERE session_id = ?",
                (session_id,),
            )
            existing_hashes = {row[0] for row in cursor.fetchall()}

            # Track new hashes to add
            new_hashes = []

            for search_result in all_results:
                # Compute hash for this result
                content = search_result.get("content", "")

                # Try to extract file_id from the result
                file_id = ""
                if "file_id" in search_result:
                    file_id = search_result["file_id"]
                elif "metadata" in search_result and "file_id" in search_result.get(
                    "metadata", {}
                ):
                    file_id = search_result["metadata"]["file_id"]

                content_hash = self.compute_content_hash_for_dedup(content, file_id)

                # Check if we've seen this content before in this session
                if content_hash not in existing_hashes:
                    existing_hashes.add(content_hash)
                    deduplicated_results.append(search_result)
                    new_hashes.append((session_id, content_hash, current_time, query))

                    # Stop when we have enough results
                    if len(deduplicated_results) >= max_results:
                        break
                else:
                    duplicate_count += 1

            # Insert new hashes into database
            if new_hashes:
                conn.executemany(
                    "INSERT OR REPLACE INTO search_dedup_cache "
                    "(session_id, content_hash, timestamp, query) VALUES (?, ?, ?, ?)",
                    new_hashes,
                )
                conn.commit()

        logger.debug(
            f"[DEDUP] Session {session_id}: {len(deduplicated_results)} unique, "
            f"{duplicate_count} duplicates from {len(all_results)} total"
        )

        return deduplicated_results, duplicate_count

    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get statistics for a session's deduplication cache."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
                FROM search_dedup_cache 
                WHERE session_id = ?
                """,
                (session_id,),
            )
            count, min_ts, max_ts = cursor.fetchone()

            return {
                "session_id": session_id,
                "unique_results_cached": count or 0,
                "oldest_entry": min_ts,
                "newest_entry": max_ts,
                "cache_age_seconds": (max_ts - min_ts) if min_ts and max_ts else 0,
            }
