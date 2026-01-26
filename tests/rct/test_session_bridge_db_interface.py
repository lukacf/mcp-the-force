"""
RCT Spike: SessionBridge Database Interface Investigation

Purpose: Validate that SessionBridge can use BaseSQLiteCache pattern
instead of aiosqlite, maintaining consistency with rest of codebase.

Key Questions:
1. Can SessionBridge inherit from BaseSQLiteCache?
2. Does thread-pool async pattern work for CLI session mappings?
3. Is there any reason to keep aiosqlite?
"""

import pytest
import tempfile
import os


class TestSessionBridgeWithBaseSQLiteCache:
    """Test SessionBridge using BaseSQLiteCache (migrated from aiosqlite)."""

    @pytest.mark.asyncio
    async def test_session_bridge_uses_base_cache(self):
        """Verify SessionBridge now uses BaseSQLiteCache pattern."""
        from mcp_the_force.cli_agents.session_bridge import SessionBridge
        from mcp_the_force.sqlite_base_cache import BaseSQLiteCache

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            bridge = SessionBridge(db_path=db_path)

            # Verify inheritance
            assert isinstance(bridge, BaseSQLiteCache)

            # Store and retrieve
            await bridge.store_cli_session_id(
                project="test-proj",
                session_id="force-123",
                cli_name="claude",
                cli_session_id="claude-abc",
            )

            result = await bridge.get_cli_session_id(
                project="test-proj",
                session_id="force-123",
                cli_name="claude",
            )

            assert result == "claude-abc"

            # Cleanup uses inherited close()
            bridge.close()


class TestBaseSQLiteCachePattern:
    """Test if BaseSQLiteCache pattern works for session mappings."""

    @pytest.mark.asyncio
    async def test_thread_pool_async_pattern(self):
        """Verify thread-pool async pattern works for simple CRUD."""
        from mcp_the_force.sqlite_base_cache import BaseSQLiteCache

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Simulate SessionBridge-like cache
            create_sql = """
                CREATE TABLE IF NOT EXISTS cli_session_mappings (
                    project TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    cli_name TEXT NOT NULL,
                    cli_session_id TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (project, session_id, cli_name)
                )
            """

            cache = BaseSQLiteCache(
                db_path=db_path,
                ttl=86400 * 180,  # 180 days
                table_name="cli_session_mappings",
                create_table_sql=create_sql,
            )

            import time

            # Insert
            await cache._execute_async(
                """
                INSERT OR REPLACE INTO cli_session_mappings
                (project, session_id, cli_name, cli_session_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("test-proj", "force-123", "claude", "claude-abc", int(time.time())),
                fetch=False,
            )

            # Retrieve
            rows = await cache._execute_async(
                """
                SELECT cli_session_id FROM cli_session_mappings
                WHERE project = ? AND session_id = ? AND cli_name = ?
                """,
                ("test-proj", "force-123", "claude"),
            )

            assert rows is not None
            assert len(rows) == 1
            assert rows[0][0] == "claude-abc"

            cache.close()


class TestMigrationPath:
    """Test migration from aiosqlite to BaseSQLiteCache."""

    @pytest.mark.asyncio
    async def test_both_can_read_same_db(self):
        """Verify both approaches can read the same SQLite file."""
        import aiosqlite
        from mcp_the_force.sqlite_base_cache import BaseSQLiteCache
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "shared.db")

            # Write with aiosqlite
            async with aiosqlite.connect(db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS cli_session_mappings (
                        project TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        cli_name TEXT NOT NULL,
                        cli_session_id TEXT NOT NULL,
                        updated_at INTEGER NOT NULL,
                        PRIMARY KEY (project, session_id, cli_name)
                    )
                """)
                await db.execute(
                    """
                    INSERT INTO cli_session_mappings
                    (project, session_id, cli_name, cli_session_id, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("proj", "sid", "claude", "cli-123", int(time.time())),
                )
                await db.commit()

            # Read with BaseSQLiteCache (sync sqlite3)
            cache = BaseSQLiteCache(
                db_path=db_path,
                ttl=86400,
                table_name="cli_session_mappings",
                create_table_sql="SELECT 1",  # Table already exists
            )

            rows = await cache._execute_async(
                "SELECT cli_session_id FROM cli_session_mappings WHERE project = ?",
                ("proj",),
            )

            assert rows is not None
            assert rows[0][0] == "cli-123"
            cache.close()


class TestMigrationCompleted:
    """Document the completed migration."""

    def test_migration_completed(self):
        """
        MIGRATION COMPLETED: SessionBridge now uses BaseSQLiteCache

        What was done:
        1. SessionBridge now inherits from BaseSQLiteCache
        2. store/get methods use _execute_async (thread-pool pattern)
        3. aiosqlite import removed
        4. aiosqlite can be removed from pyproject.toml

        Benefits achieved:
        1. Consistency - all SQLite access uses same pattern
        2. Proven pattern - thread-pool async already tested
        3. Fewer dependencies - aiosqlite no longer required
        4. Simpler maintenance - one DB pattern to understand

        Data migration:
        - Not needed - same SQLite format, same table schema
        - updated_at changed from TIMESTAMP to INTEGER (epoch) for consistency
        """
        from mcp_the_force.cli_agents.session_bridge import SessionBridge
        from mcp_the_force.sqlite_base_cache import BaseSQLiteCache

        # Verify migration completed
        assert issubclass(SessionBridge, BaseSQLiteCache)
