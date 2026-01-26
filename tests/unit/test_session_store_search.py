"""Unit tests for session store search with the current UnifiedSessionCache schema.

This tests the integration between history/config.py and the actual
unified_sessions table schema, where 'tool' is stored per-message in
the JSON history, NOT as a separate column.
"""

import tempfile
import sqlite3
import json
from pathlib import Path

import pytest

from mcp_the_force.history.config import HistoryStorageConfig


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
def db_with_current_schema(temp_db):
    """Create a database with the CURRENT unified_sessions schema.

    The current schema does NOT have a 'tool' column - tool is stored
    per-message in the history JSON field.
    """
    conn = sqlite3.connect(temp_db)

    # Create unified_sessions table with CURRENT schema (no tool column!)
    conn.execute("""
        CREATE TABLE unified_sessions(
            project      TEXT NOT NULL,
            session_id   TEXT NOT NULL,
            history      TEXT,
            provider_metadata TEXT,
            updated_at   INTEGER NOT NULL,
            PRIMARY KEY (project, session_id)
        )
    """)

    # Create stores table (for vector stores)
    conn.execute("""
        CREATE TABLE stores (
            store_id TEXT PRIMARY KEY,
            store_type TEXT NOT NULL CHECK(store_type IN ('conversation','commit')),
            doc_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            is_active INTEGER NOT NULL CHECK(is_active IN (0,1))
        )
    """)

    # Create history_meta table
    conn.execute("""
        CREATE TABLE history_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Insert sample sessions with tool stored IN the history JSON (current format)
    test_sessions = [
        {
            "project": "mcp-the-force",
            "session_id": "memory-vault-diagnostic",
            "history": json.dumps(
                [
                    {
                        "role": "user",
                        "content": "ZEPHYR-NEXUS-QUANTUM-7734: Memory vault test",
                        "tool": "chat_with_gemini3_flash_preview",
                    },
                    {
                        "role": "assistant",
                        "content": "ECHO-PROTOCOL-OMEGA confirmed",
                        "tool": "chat_with_gemini3_flash_preview",
                    },
                ]
            ),
            "updated_at": 1234567890,
        },
        {
            "project": "mcp-the-force",
            "session_id": "ollama-debug-session",
            "history": json.dumps(
                [
                    {
                        "role": "user",
                        "content": "Debug ollama_chat prefix issue",
                        "tool": "chat_with_gpt52",
                    },
                    {
                        "role": "assistant",
                        "content": "LiteLLM recommends ollama_chat for better responses",
                        "tool": "chat_with_gpt52",
                    },
                ]
            ),
            "updated_at": 1234567891,
        },
        {
            "project": "mcp-the-force",
            "session_id": "cross-tool-session",
            "history": json.dumps(
                [
                    {
                        "role": "user",
                        "content": "Start with GPT",
                        "tool": "chat_with_gpt52",
                    },
                    {
                        "role": "assistant",
                        "content": "GPT response",
                        "tool": "chat_with_gpt52",
                    },
                    {
                        "role": "user",
                        "content": "Continue with Gemini",
                        "tool": "chat_with_gemini3_pro_preview",
                    },
                    {
                        "role": "assistant",
                        "content": "Gemini response",
                        "tool": "chat_with_gemini3_pro_preview",
                    },
                ]
            ),
            "updated_at": 1234567892,
        },
        {
            "project": "mcp-the-force",
            "session_id": "work-with-session",
            "history": json.dumps(
                [
                    {
                        "role": "user",
                        "content": "Use work_with tool",
                        "tool": "work_with",
                    },
                    {
                        "role": "assistant",
                        "content": "work_with response",
                        "tool": "work_with",
                    },
                ]
            ),
            "updated_at": 1234567893,
        },
    ]

    for session in test_sessions:
        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (
                session["project"],
                session["session_id"],
                session["history"],
                session["updated_at"],
            ),
        )

    # Insert a traditional vector store
    conn.execute(
        "INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active) "
        "VALUES (?, ?, ?, ?, ?)",
        ("vs_traditional_store", "conversation", 5, "2024-01-01", 1),
    )

    conn.commit()
    conn.close()

    return temp_db


class TestSessionSearchWithCurrentSchema:
    """Test session search with the actual current UnifiedSessionCache schema."""

    def test_session_search_finds_sessions_without_tool_column(
        self, db_with_current_schema
    ):
        """Test that session search works when tool is in history JSON, not a column.

        This is a regression test for the schema mismatch bug where the query
        referenced a 'tool' column that doesn't exist in the current schema.
        """
        config = HistoryStorageConfig(db_path=db_with_current_schema)

        # Get session stores - should find sessions even without tool column
        stores = config.get_stores_with_types(["session"])

        # Should find sessions (at least some of them)
        assert len(stores) > 0, (
            "Session search returned no results. The query likely failed because "
            "it references a 'tool' column that doesn't exist in the current schema."
        )

    def test_session_search_extracts_tool_from_history_json(
        self, db_with_current_schema
    ):
        """Test that session search correctly extracts tool from history JSON."""
        config = HistoryStorageConfig(db_path=db_with_current_schema)

        stores = config.get_stores_with_types(["session"])
        store_ids = [store[1] for store in stores]

        # Should find sessions that have chat_with_* tools in their history
        # The store_id format is project||session_id (tool is not in the ID)
        # We expect 3 sessions: memory-vault-diagnostic, ollama-debug-session, cross-tool-session
        # (work-with-session is excluded because it only has work_with tool, not chat_with_*)
        assert len(store_ids) >= 3, (
            f"Expected at least 3 sessions with chat_with_* tools, found {len(store_ids)}. "
            f"Store IDs: {store_ids}"
        )

        # Verify the expected sessions are present
        expected_sessions = [
            "memory-vault-diagnostic",
            "ollama-debug-session",
            "cross-tool-session",
        ]
        for session in expected_sessions:
            assert any(
                session in sid for sid in store_ids
            ), f"Expected session '{session}' not found in store IDs: {store_ids}"

    def test_session_search_filters_non_chat_tools(self, db_with_current_schema):
        """Test that session search only returns chat_with_* tool sessions."""
        config = HistoryStorageConfig(db_path=db_with_current_schema)

        stores = config.get_stores_with_types(["session"])
        store_ids = [store[1] for store in stores]

        # Should NOT find work_with sessions
        work_with_sessions = [sid for sid in store_ids if "work_with" in sid]
        assert (
            len(work_with_sessions) == 0
        ), f"work_with sessions should be filtered out, but found: {work_with_sessions}"

    def test_session_search_handles_cross_tool_sessions(self, db_with_current_schema):
        """Test that cross-tool sessions are handled correctly.

        A session may have messages from multiple tools. The search should
        find sessions that have ANY chat_with_* tool in their history.
        """
        config = HistoryStorageConfig(db_path=db_with_current_schema)

        stores = config.get_stores_with_types(["session"])
        store_ids = [store[1] for store in stores]

        # The cross-tool session should be found (it has chat_with_* tools)
        cross_tool_found = any("cross-tool-session" in sid for sid in store_ids)
        assert cross_tool_found, f"Cross-tool session not found. Store IDs: {store_ids}"

    def test_conversation_search_excludes_sessions(self, db_with_current_schema):
        """Test that conversation search doesn't include unified sessions."""
        config = HistoryStorageConfig(db_path=db_with_current_schema)

        # Conversation searches should only return vector stores
        stores = config.get_stores_with_types(["conversation"])

        # Should only have the traditional vector store
        assert len(stores) == 1
        assert stores[0][1] == "vs_traditional_store"


class TestSessionSearchEdgeCases:
    """Edge case tests for session search."""

    def test_session_search_with_empty_history(self, temp_db):
        """Test that sessions with empty history are excluded."""
        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE unified_sessions(
                project TEXT NOT NULL,
                session_id TEXT NOT NULL,
                history TEXT,
                provider_metadata TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (project, session_id)
            )
        """)
        conn.execute("""
            CREATE TABLE stores (
                store_id TEXT PRIMARY KEY,
                store_type TEXT NOT NULL,
                doc_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE history_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)
        """)

        # Insert sessions with various empty states
        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("test", "null-history", None, 1234567890),
        )
        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("test", "empty-string", "", 1234567891),
        )
        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("test", "empty-array", "[]", 1234567892),
        )
        conn.commit()
        conn.close()

        config = HistoryStorageConfig(db_path=temp_db)
        stores = config.get_stores_with_types(["session"])

        # None of these should be returned
        assert (
            len(stores) == 0
        ), f"Empty sessions should be excluded, but found: {stores}"

    def test_session_search_with_malformed_json(self, temp_db):
        """Test that sessions with malformed JSON history don't crash the search."""
        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE unified_sessions(
                project TEXT NOT NULL,
                session_id TEXT NOT NULL,
                history TEXT,
                provider_metadata TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (project, session_id)
            )
        """)
        conn.execute("""
            CREATE TABLE stores (
                store_id TEXT PRIMARY KEY,
                store_type TEXT NOT NULL,
                doc_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE history_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)
        """)

        # Insert session with malformed JSON
        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("test", "malformed", "not valid json {{{", 1234567890),
        )
        conn.commit()
        conn.close()

        config = HistoryStorageConfig(db_path=temp_db)

        # Should not crash, should just return empty or skip the malformed session
        stores = config.get_stores_with_types(["session"])
        # The malformed session should be excluded
        assert all(
            "malformed" not in s[1] for s in stores
        ), f"Malformed session should be excluded: {stores}"
