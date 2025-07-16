"""Base class for SQLite-backed caches with common functionality."""

import sqlite3
import time
import random
import threading
import logging
from typing import Optional, Any, List
from .utils.thread_pool import run_in_thread_pool

logger = logging.getLogger(__name__)


class BaseSQLiteCache:
    """Base class for SQLite caches with async-safe database operations."""

    def __init__(
        self,
        db_path: str,
        ttl: int,
        table_name: str,
        create_table_sql: str,
        purge_probability: float = 0.01,
    ):
        """Initialize the cache with common SQLite setup.

        Args:
            db_path: Path to the SQLite database file
            ttl: Time-to-live for cache entries in seconds
            table_name: Name of the table for this cache
            create_table_sql: SQL statement to create the table
            purge_probability: Probability of running cleanup on write operations
        """
        self.db_path = db_path
        self.ttl = ttl
        self.table_name = table_name
        self.purge_probability = purge_probability
        self._lock = threading.RLock()

        try:
            # check_same_thread=False allows other threads to reuse connection
            self._conn = sqlite3.connect(
                db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False
            )
            self._init_db(create_table_sql)
            logger.info(f"{self.__class__.__name__} using SQLite at {db_path}")
        except sqlite3.Error as e:
            raise RuntimeError(f"SQLite init failed: {e}") from e

    def _init_db(self, create_table_sql: str):
        """Initialize database with common pragmas and table creation."""
        with self._conn:
            # Execute pragmas first
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=5000")

            # Create the table
            self._conn.execute(create_table_sql)

            # Create the index
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_updated "
                f"ON {self.table_name}(updated_at)"
            )

    async def _execute_async(
        self, query: str, params: tuple = (), fetch: bool = True
    ) -> Optional[List[Any]]:
        """Execute a query asynchronously without blocking the event loop.

        Args:
            query: SQL query to execute
            params: Query parameters
            fetch: If True, fetch and return results

        Returns:
            Query results if fetch=True, None otherwise
        """

        def _sync_execute():
            with self._lock, self._conn:
                cursor = self._conn.execute(query, params)
                if fetch:
                    return cursor.fetchall()
                return None

        # Run in shared thread pool to avoid blocking event loop
        result = await run_in_thread_pool(_sync_execute)
        return result  # type: ignore[no-any-return]

    async def _probabilistic_cleanup(self):
        """Run cleanup with configured probability."""
        if random.random() < self.purge_probability:
            cutoff = int(time.time()) - self.ttl
            await self._execute_async(
                f"DELETE FROM {self.table_name} WHERE updated_at < ?",
                (cutoff,),
                fetch=False,
            )
            logger.debug(f"Performed probabilistic cleanup on {self.table_name}")

    def _validate_session_id(self, session_id: str):
        """Validate session ID length."""
        if len(session_id) > 1024:
            raise ValueError("session_id too long")

    def close(self) -> None:
        """Close the database connection safely."""
        # Acquire the lock to ensure no other threads are using the connection.
        with self._lock:
            try:
                # The connection object might already be None if close() is called multiple times
                if hasattr(self, "_conn") and self._conn:
                    self._conn.close()
                    self._conn = None  # type: ignore[assignment] # Prevent reuse after closing
                    logger.info(f"Closed SQLite connection to {self.db_path}")
            except sqlite3.Error as e:
                # Log the specific error instead of silently passing.
                logger.error(f"Error closing SQLite connection for {self.db_path}: {e}")
