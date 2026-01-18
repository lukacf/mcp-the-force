"""
SessionBridge: Maps Force session_id to CLI-native session identifiers.

Stores mappings in SQLite for persistence across process restarts.
"""

import aiosqlite
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionMapping:
    """A mapping from Force session to CLI session."""

    project: str
    session_id: str
    cli_name: str
    cli_session_id: str


class SessionBridge:
    """
    Manages session ID mappings between Force and CLI agents.

    Different CLIs use different session concepts:
    - Claude: session_id in JSON output
    - Gemini: session_id in JSON output
    - Codex: thread_id (NOT session_id) in JSONL output
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize SessionBridge with optional custom database path."""
        if db_path == ":memory:":
            self._db_path = ":memory:"
        elif db_path:
            self._db_path = db_path
        else:
            # Default: use project-local storage
            default_dir = Path.home() / ".mcp-the-force"
            default_dir.mkdir(parents=True, exist_ok=True)
            self._db_path = str(default_dir / "cli_sessions.db")

        self._initialized = False
        # Persistent connection for :memory: databases (each connect() creates new db)
        self._persistent_conn: Optional[aiosqlite.Connection] = None

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get a database connection, reusing persistent connection for :memory:."""
        if self._db_path == ":memory:":
            if self._persistent_conn is None:
                self._persistent_conn = await aiosqlite.connect(self._db_path)
            return self._persistent_conn
        return await aiosqlite.connect(self._db_path)

    async def _release_connection(self, conn: aiosqlite.Connection) -> None:
        """Release a connection (close it unless it's the persistent one)."""
        if self._db_path != ":memory:":
            await conn.close()

    async def _ensure_initialized(self) -> None:
        """Ensure the database schema exists."""
        if self._initialized:
            return

        conn = await self._get_connection()
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cli_session_mappings (
                    project TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    cli_name TEXT NOT NULL,
                    cli_session_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (project, session_id, cli_name)
                )
            """)
            await conn.commit()
        finally:
            await self._release_connection(conn)

        self._initialized = True

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
        await self._ensure_initialized()

        conn = await self._get_connection()
        try:
            await conn.execute(
                """
                INSERT INTO cli_session_mappings (project, session_id, cli_name, cli_session_id, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (project, session_id, cli_name)
                DO UPDATE SET cli_session_id = excluded.cli_session_id,
                              updated_at = CURRENT_TIMESTAMP
                """,
                (project, session_id, cli_name, cli_session_id),
            )
            await conn.commit()
        finally:
            await self._release_connection(conn)

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
        await self._ensure_initialized()

        conn = await self._get_connection()
        try:
            cursor = await conn.execute(
                """
                SELECT cli_session_id FROM cli_session_mappings
                WHERE project = ? AND session_id = ? AND cli_name = ?
                """,
                (project, session_id, cli_name),
            )
            row = await cursor.fetchone()
        finally:
            await self._release_connection(conn)

        if row:
            cli_session_id: str = row[0]
            logger.debug(
                f"Found CLI session mapping: {project}/{session_id}/{cli_name} -> {cli_session_id}"
            )
            return cli_session_id

        logger.debug(f"No CLI session mapping found: {project}/{session_id}/{cli_name}")
        return None

    async def close(self) -> None:
        """Close any persistent connections."""
        if self._persistent_conn is not None:
            await self._persistent_conn.close()
            self._persistent_conn = None
