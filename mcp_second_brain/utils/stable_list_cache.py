"""Stable list cache for context overflow management."""

import os
import time
import json
import logging
import asyncio
from typing import Optional, List, Dict, Tuple

from mcp_second_brain.config import get_settings
from mcp_second_brain.sqlite_base_cache import BaseSQLiteCache

logger = logging.getLogger(__name__)


class StableListCache(BaseSQLiteCache):
    """SQLite-backed cache for stable inline lists and sent file tracking."""

    def __init__(self, db_path: Optional[str] = None, ttl: Optional[int] = None):
        if db_path is None:
            settings = get_settings()
            # Use the same database as session cache for simplicity
            db_path = settings.session_db_path
        if ttl is None:
            settings = get_settings()
            ttl = settings.session_ttl_seconds

        # Create stable_inline_lists table SQL
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS stable_inline_lists (
            session_id TEXT PRIMARY KEY,
            inline_paths TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """

        super().__init__(
            db_path=db_path,
            ttl=ttl,
            table_name="stable_inline_lists",  # Primary table for cleanup
            create_table_sql=create_table_sql,
            purge_probability=get_settings().session_cleanup_probability,
        )

        # Create additional tables for sent files tracking
        self._create_additional_tables()

    def _create_additional_tables(self):
        """Create additional tables specific to stable list cache."""
        with self._conn:
            # Create sent files tracking table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_files (
                    session_id TEXT,
                    file_path TEXT,
                    last_size INTEGER NOT NULL,
                    last_mtime INTEGER NOT NULL,
                    PRIMARY KEY (session_id, file_path)
                )
            """)

            # Create index for sent_files lookup
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sent_files_session 
                ON sent_files(session_id)
            """)

    def _validate_session_id(self, session_id: str):
        """Validate session ID format."""
        if not session_id or len(session_id) > 256:
            raise ValueError(f"Invalid session_id: {session_id}")

    async def get_stable_list(self, session_id: str) -> Optional[List[str]]:
        """Get the stable inline list for a session."""
        self._validate_session_id(session_id)

        now = int(time.time())

        rows = await self._execute_async(
            "SELECT inline_paths, updated_at FROM stable_inline_lists WHERE session_id = ?",
            (session_id,),
        )

        if not rows:
            logger.info(f"No stable list found for session {session_id}")
            return None

        inline_paths_json, updated_at = rows[0][0], rows[0][1]

        # Check if expired
        if now - updated_at >= self.ttl:
            await self._execute_async(
                "DELETE FROM stable_inline_lists WHERE session_id = ?",
                (session_id,),
                fetch=False,
            )
            await self._execute_async(
                "DELETE FROM sent_files WHERE session_id = ?",
                (session_id,),
                fetch=False,
            )
            logger.info(f"Expired stable list for session {session_id}")
            return None

        paths: List[str] = json.loads(inline_paths_json)
        return paths

    async def save_stable_list(self, session_id: str, inline_paths: List[str]):
        """Save the stable inline list for a session."""
        self._validate_session_id(session_id)

        now = int(time.time())
        inline_paths_json = json.dumps(inline_paths)

        await self._execute_async(
            "REPLACE INTO stable_inline_lists(session_id, inline_paths, created_at, updated_at) VALUES(?, ?, ?, ?)",
            (session_id, inline_paths_json, now, now),
            fetch=False,
        )
        logger.info(
            f"Saved stable list with {len(inline_paths)} files for session {session_id}"
        )

        # Probabilistic cleanup
        await self._probabilistic_cleanup()

    async def get_sent_file_info(
        self, session_id: str, file_path: str
    ) -> Optional[Dict[str, int]]:
        """Get the last sent info for a file."""
        self._validate_session_id(session_id)

        rows = await self._execute_async(
            "SELECT last_size, last_mtime FROM sent_files WHERE session_id = ? AND file_path = ?",
            (session_id, file_path),
        )

        if not rows:
            return None

        return {"size": rows[0][0], "mtime": rows[0][1]}

    async def update_sent_file_info(
        self, session_id: str, file_path: str, size: int, mtime: int
    ):
        """Update the sent info for a file."""
        self._validate_session_id(session_id)

        await self._execute_async(
            "REPLACE INTO sent_files(session_id, file_path, last_size, last_mtime) VALUES(?, ?, ?, ?)",
            (session_id, file_path, size, mtime),
            fetch=False,
        )
        logger.debug(f"Updated sent info for {file_path} in session {session_id}")

    async def batch_update_sent_files(
        self, session_id: str, files_info: List[Tuple[str, int, int]]
    ):
        """Batch update sent info for multiple files."""
        self._validate_session_id(session_id)

        # Use executemany for efficiency
        def _sync_batch_update():
            with self._lock, self._conn:
                self._conn.executemany(
                    "REPLACE INTO sent_files(session_id, file_path, last_size, last_mtime) VALUES(?, ?, ?, ?)",
                    [
                        (session_id, path, size, mtime)
                        for path, size, mtime in files_info
                    ],
                )

        await asyncio.to_thread(_sync_batch_update)
        logger.debug(f"Batch updated {len(files_info)} files for session {session_id}")

    async def file_changed_since_last_send(
        self, session_id: str, file_path: str
    ) -> bool:
        """Check if a file has changed since it was last sent."""
        last_info = await self.get_sent_file_info(session_id, file_path)

        if not last_info:
            # Never sent before
            return True

        try:
            stat = os.stat(file_path)
            current_size = stat.st_size
            current_mtime = int(stat.st_mtime)

            return (
                current_size != last_info["size"] or current_mtime != last_info["mtime"]
            )
        except OSError:
            # File doesn't exist or can't be accessed
            logger.warning(f"Cannot stat file {file_path}")
            return True

    async def reset_session(self, session_id: str):
        """Reset all data for a session."""
        self._validate_session_id(session_id)

        await self._execute_async(
            "DELETE FROM stable_inline_lists WHERE session_id = ?",
            (session_id,),
            fetch=False,
        )
        await self._execute_async(
            "DELETE FROM sent_files WHERE session_id = ?",
            (session_id,),
            fetch=False,
        )
        logger.info(f"Reset all data for session {session_id}")

    async def _probabilistic_cleanup(self):
        """Clean up expired entries from both tables."""
        await super()._probabilistic_cleanup()

        # Also clean up sent_files table
        cutoff = int(time.time()) - self.ttl
        await self._execute_async(
            """DELETE FROM sent_files WHERE session_id IN 
               (SELECT session_id FROM stable_inline_lists WHERE updated_at < ?)""",
            (cutoff,),
            fetch=False,
        )
