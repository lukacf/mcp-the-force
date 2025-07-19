"""Configuration management for project memory system."""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from datetime import datetime, timezone

from ..config import get_settings
from ..utils.vector_store import get_client

logger = logging.getLogger(__name__)


class MemoryConfig:
    """Manages memory store configuration and rollover using SQLite."""

    def __init__(self, db_path: Optional[Path] = None):
        settings = get_settings()

        # SQLite database path (defaults to session cache DB)
        self.db_path = db_path or Path(settings.session_db_path)

        self._client = get_client()
        self._lock = threading.RLock()
        self._rollover_limit = settings.memory_rollover_limit

        # Initialize database connection
        self._db = sqlite3.connect(
            self.db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False
        )
        self._db.row_factory = sqlite3.Row

        # Initialize schema
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with self._db:
            self._db.executescript("""
                -- Same pragmas as session cache
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                PRAGMA busy_timeout=5000;
                
                -- Main stores table
                CREATE TABLE IF NOT EXISTS stores (
                    store_id      TEXT PRIMARY KEY,
                    store_type    TEXT NOT NULL CHECK(store_type IN ('conversation','commit')),
                    doc_count     INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL,
                    is_active     INTEGER NOT NULL CHECK(is_active IN (0,1))
                );
                
                -- Ensure exactly one active store per type
                CREATE UNIQUE INDEX IF NOT EXISTS idx_active_store
                  ON stores (store_type) WHERE is_active = 1;
                
                -- Metadata table
                CREATE TABLE IF NOT EXISTS memory_meta(
                    key         TEXT PRIMARY KEY,
                    value       TEXT NOT NULL
                );
                
                -- Convenient view for active stores
                CREATE VIEW IF NOT EXISTS active_stores AS
                  SELECT store_type, store_id, doc_count
                    FROM stores WHERE is_active = 1;
            """)

            # Initialize metadata if not exists
            row = self._db.execute("SELECT COUNT(*) FROM memory_meta").fetchone()
            if row[0] == 0:
                now = datetime.now(timezone.utc).isoformat()
                self._db.executemany(
                    "INSERT INTO memory_meta(key, value) VALUES(?, ?)",
                    [("created_at", now), ("last_gc", now)],
                )

    def _get_active_store(self, store_type: str) -> Tuple[str, int]:
        """Get active store ID and count for given type."""
        row = self._db.execute(
            """
            SELECT store_id, doc_count FROM stores
            WHERE store_type = ? AND is_active = 1
        """,
            (store_type,),
        ).fetchone()

        if row:
            return row["store_id"], row["doc_count"]
        return "", 0

    def _create_store(self, store_type: str, store_num: int) -> str:
        """Create a new vector store."""
        name = f"project-{store_type}s-{store_num:03d}"
        # Create with 365 day expiration as backup protection
        # (cleanup tools should skip based on name prefix anyway)
        store = self._client.vector_stores.create(
            name=name, expires_after={"anchor": "last_active_at", "days": 365}
        )
        store_id: str = store.id
        return store_id

    def _rollover_store(self, store_type: str) -> str:
        """Create new store and mark it as active."""
        # Count existing stores of this type
        count = self._db.execute(
            "SELECT COUNT(*) FROM stores WHERE store_type = ?", (store_type,)
        ).fetchone()[0]

        # Create new store
        store_id = self._create_store(store_type, count + 1)

        # Update database in a transaction
        with self._db:
            # Deactivate current active store
            self._db.execute(
                "UPDATE stores SET is_active = 0 WHERE store_type = ? AND is_active = 1",
                (store_type,),
            )

            # Insert new active store
            self._db.execute(
                """
                INSERT INTO stores(store_id, store_type, doc_count, created_at, is_active)
                VALUES(?, ?, 0, ?, 1)
            """,
                (store_id, store_type, datetime.now(timezone.utc).isoformat()),
            )

        return store_id

    def get_active_conversation_store(self) -> str:
        """Get active conversation store ID, creating if needed."""
        with self._lock:
            store_id, count = self._get_active_store("conversation")

            # Create first store if none exist
            if not store_id:
                store_id = self._create_store("conversation", 1)
                with self._db:
                    self._db.execute(
                        """
                        INSERT INTO stores(store_id, store_type, doc_count, created_at, is_active)
                        VALUES(?, 'conversation', 0, ?, 1)
                    """,
                        (store_id, datetime.now(timezone.utc).isoformat()),
                    )
                return store_id

            # Check if rollover needed
            if count >= self._rollover_limit:
                return self._rollover_store("conversation")

            return store_id

    def get_active_commit_store(self) -> str:
        """Get active commit store ID, creating if needed."""
        with self._lock:
            store_id, count = self._get_active_store("commit")

            # Create first store if none exist
            if not store_id:
                store_id = self._create_store("commit", 1)
                with self._db:
                    self._db.execute(
                        """
                        INSERT INTO stores(store_id, store_type, doc_count, created_at, is_active)
                        VALUES(?, 'commit', 0, ?, 1)
                    """,
                        (store_id, datetime.now(timezone.utc).isoformat()),
                    )
                return store_id

            # Check if rollover needed
            if count >= self._rollover_limit:
                return self._rollover_store("commit")

            return store_id

    def increment_conversation_count(self):
        """Increment document count for active conversation store."""
        with self._lock:
            with self._db:
                self._db.execute("""
                    UPDATE stores SET doc_count = doc_count + 1
                    WHERE store_type = 'conversation' AND is_active = 1
                """)

    def increment_commit_count(self):
        """Increment document count for active commit store."""
        with self._lock:
            with self._db:
                self._db.execute("""
                    UPDATE stores SET doc_count = doc_count + 1
                    WHERE store_type = 'commit' AND is_active = 1
                """)

    def get_all_store_ids(self) -> List[str]:
        """Get all store IDs for querying."""
        with self._lock:
            rows = self._db.execute("SELECT store_id FROM stores").fetchall()
            return [row["store_id"] for row in rows]

    def get_store_ids_by_type(self, store_types: List[str]) -> List[str]:
        """Get store IDs filtered by type."""
        with self._lock:
            if not store_types:
                return []
            placeholders = ",".join("?" for _ in store_types)
            query = f"SELECT store_id FROM stores WHERE store_type IN ({placeholders})"
            rows = self._db.execute(query, store_types).fetchall()
            return [row["store_id"] for row in rows]

    def close(self):
        """Close database connection."""
        if hasattr(self, "_db"):
            self._db.close()

    def __del__(self):
        """Ensure database connection is closed."""
        self.close()


# Global instance and lock
# Use a dict to store per-path instances for test isolation
_memory_configs: Dict[str, MemoryConfig] = {}
_memory_config_lock = threading.RLock()


def get_memory_config() -> MemoryConfig:
    """Get or create global memory configuration instance."""
    global _memory_configs

    # Get the current session DB path
    settings = get_settings()
    db_path = settings.session_db_path

    with _memory_config_lock:
        if db_path not in _memory_configs:
            _memory_configs[db_path] = MemoryConfig()
        return _memory_configs[db_path]
