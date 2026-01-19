"""
SessionBridge: Maps Force session_id to CLI-native session identifiers.

Stores mappings in SQLite for persistence across process restarts.
Uses BaseSQLiteCache for consistency with the rest of the codebase.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mcp_the_force.sqlite_base_cache import BaseSQLiteCache

logger = logging.getLogger(__name__)

# 6 months TTL for session mappings
SESSION_MAPPING_TTL = 86400 * 180

CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS cli_session_mappings (
        project TEXT NOT NULL,
        session_id TEXT NOT NULL,
        cli_name TEXT NOT NULL,
        cli_session_id TEXT NOT NULL,
        updated_at INTEGER NOT NULL,
        PRIMARY KEY (project, session_id, cli_name)
    )
"""


@dataclass
class SessionMapping:
    """A mapping from Force session to CLI session."""

    project: str
    session_id: str
    cli_name: str
    cli_session_id: str


class SessionBridge(BaseSQLiteCache):
    """
    Manages session ID mappings between Force and CLI agents.

    Different CLIs use different session concepts:
    - Claude: session_id in JSON output
    - Gemini: session_id in JSON output
    - Codex: thread_id (NOT session_id) in JSONL output

    Inherits from BaseSQLiteCache for consistent async-safe SQLite access.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize SessionBridge with optional custom database path."""
        if db_path is None:
            # Default: use project-local storage
            default_dir = Path.home() / ".mcp-the-force"
            default_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(default_dir / "cli_sessions.db")

        super().__init__(
            db_path=db_path,
            ttl=SESSION_MAPPING_TTL,
            table_name="cli_session_mappings",
            create_table_sql=CREATE_TABLE_SQL,
            purge_probability=0.01,
        )

    async def store_cli_session_id(
        self,
        project: str,
        session_id: str,
        cli_name: str,
        cli_session_id: str,
    ) -> None:
        """
        Store a CLI session ID mapping.

        Args:
            project: Project identifier
            session_id: Force session ID
            cli_name: CLI name (claude, gemini, codex)
            cli_session_id: Native CLI session ID
        """
        await self._execute_async(
            """
            INSERT INTO cli_session_mappings (project, session_id, cli_name, cli_session_id, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (project, session_id, cli_name)
            DO UPDATE SET cli_session_id = excluded.cli_session_id,
                          updated_at = excluded.updated_at
            """,
            (project, session_id, cli_name, cli_session_id, int(time.time())),
            fetch=False,
        )

        # Probabilistic cleanup of old entries
        await self._probabilistic_cleanup()

        logger.debug(
            f"Stored CLI session mapping: {project}/{session_id}/{cli_name} -> {cli_session_id}"
        )

    async def get_cli_session_id(
        self,
        project: str,
        session_id: str,
        cli_name: str,
    ) -> Optional[str]:
        """
        Retrieve a CLI session ID for the given Force session.

        Args:
            project: Project identifier
            session_id: Force session ID
            cli_name: CLI name (claude, gemini, codex)

        Returns:
            The CLI session ID if found, None otherwise.
        """
        rows = await self._execute_async(
            """
            SELECT cli_session_id FROM cli_session_mappings
            WHERE project = ? AND session_id = ? AND cli_name = ?
            """,
            (project, session_id, cli_name),
        )

        if rows and len(rows) > 0:
            cli_session_id: str = rows[0][0]
            logger.debug(
                f"Found CLI session mapping: {project}/{session_id}/{cli_name} -> {cli_session_id}"
            )
            return cli_session_id

        logger.debug(f"No CLI session mapping found: {project}/{session_id}/{cli_name}")
        return None
