"""Unit tests for unified session search functionality."""

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
def populated_db(temp_db):
    """Create a database with unified session data."""
    # Create the tables
    conn = sqlite3.connect(temp_db)

    # Create unified_sessions table
    conn.execute("""
        CREATE TABLE unified_sessions(
            project TEXT NOT NULL,
            tool TEXT NOT NULL,
            session_id TEXT NOT NULL,
            history TEXT,
            provider_metadata TEXT,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (project, tool, session_id)
        )
    """)

    # Create stores table
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

    # Insert sample Force conversation sessions
    test_conversations = [
        {
            "project": "mcp-the-force",
            "tool": "chat_with_gemini25_flash",
            "session_id": "memory-vault-diagnostic",
            "history": json.dumps(
                [
                    {
                        "role": "user",
                        "content": "ZEPHYR-NEXUS-QUANTUM-7734: Memory vault test",
                    },
                    {"role": "assistant", "content": "ECHO-PROTOCOL-OMEGA confirmed"},
                ]
            ),
            "updated_at": 1234567890,
        },
        {
            "project": "mcp-the-force",
            "tool": "chat_with_o3",
            "session_id": "ollama-debug-session",
            "history": json.dumps(
                [
                    {"role": "user", "content": "Debug ollama_chat prefix issue"},
                    {
                        "role": "assistant",
                        "content": "LiteLLM recommends ollama_chat for better responses",
                    },
                ]
            ),
            "updated_at": 1234567891,
        },
        {
            "project": "mcp-the-force",
            "tool": "chat_with_grok4",
            "session_id": "architecture-discussion",
            "history": json.dumps(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Explain the adapter architecture"}
                        ],
                    },
                    {
                        "role": "assistant",
                        "content": "The adapter system uses protocol-based design",
                    },
                ]
            ),
            "updated_at": 1234567892,
        },
    ]

    for conv in test_conversations:
        conn.execute(
            "INSERT INTO unified_sessions (project, tool, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                conv["project"],
                conv["tool"],
                conv["session_id"],
                conv["history"],
                conv["updated_at"],
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


class TestStoreDiscoveryIntegration:
    """Test store discovery integration with unified sessions."""

    def test_store_discovery_includes_force_conversations(self, populated_db):
        """Test that store discovery correctly includes Force conversations."""
        config = HistoryStorageConfig(db_path=populated_db)

        # Get conversation stores
        stores = config.get_stores_with_types(["conversation"])

        # Should include traditional store + 3 Force conversation sessions
        assert len(stores) == 4

        store_ids = [store[1] for store in stores]
        assert "vs_traditional_store" in store_ids
        assert (
            "mcp-the-force||chat_with_gemini25_flash||memory-vault-diagnostic"
            in store_ids
        )
        assert "mcp-the-force||chat_with_o3||ollama-debug-session" in store_ids
        assert "mcp-the-force||chat_with_grok4||architecture-discussion" in store_ids


class TestRegressionPrevention:
    """Tests to prevent regression of Force conversation discovery."""

    def test_unified_sessions_always_discovered_for_conversation_searches(
        self, populated_db
    ):
        """REGRESSION TEST: Ensure unified sessions are always discovered when searching conversations."""
        config = HistoryStorageConfig(db_path=populated_db)

        # This test ensures that any conversation search includes Force sessions
        conversation_stores = config.get_stores_with_types(["conversation"])
        unified_session_stores = [
            store
            for store in conversation_stores
            if "||" in store[1] and "chat_with_" in store[1]
        ]

        # Must find at least the Force conversation sessions we inserted
        assert len(unified_session_stores) >= 3, (
            f"Expected at least 3 Force conversation sessions, got {len(unified_session_stores)}. "
            f"This indicates a regression in unified session discovery."
        )

        # Verify the store IDs have correct format
        for store_type, store_id in unified_session_stores:
            assert store_type == "conversation"
            parts = store_id.split("||")
            assert len(parts) == 3, f"Invalid store ID format: {store_id}"
            assert parts[1].startswith("chat_with_"), f"Not a chat tool: {parts[1]}"

    def test_commit_searches_exclude_unified_sessions(self, populated_db):
        """REGRESSION TEST: Ensure unified sessions only appear for conversation searches."""
        config = HistoryStorageConfig(db_path=populated_db)

        # Commit searches should not include Force conversations
        commit_stores = config.get_stores_with_types(["commit"])
        unified_session_stores = [store for store in commit_stores if "||" in store[1]]

        assert len(unified_session_stores) == 0, (
            "Unified sessions should not appear in commit store searches. "
            "This indicates a regression in store type filtering."
        )

    def test_empty_history_sessions_excluded(self, temp_db):
        """REGRESSION TEST: Ensure sessions without history are excluded."""
        config = HistoryStorageConfig(db_path=temp_db)

        # Setup database with sessions that should be excluded
        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE unified_sessions(
                project TEXT NOT NULL,
                tool TEXT NOT NULL,
                session_id TEXT NOT NULL,
                history TEXT,
                provider_metadata TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (project, tool, session_id)
            )
        """)

        # Insert sessions that should be excluded
        excluded_sessions = [
            ("mcp-the-force", "chat_with_gemini25_flash", "null-history", None),
            ("mcp-the-force", "chat_with_o3", "empty-history", ""),
            ("mcp-the-force", "chat_with_grok4", "whitespace-history", "   "),
        ]

        for i, (project, tool, session_id, history) in enumerate(excluded_sessions):
            conn.execute(
                "INSERT INTO unified_sessions (project, tool, session_id, history, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (project, tool, session_id, history, 1234567890 + i),
            )

        conn.commit()
        conn.close()

        # Get conversation stores - should exclude all empty history sessions
        stores = config.get_stores_with_types(["conversation"])
        store_ids = [store[1] for store in stores]

        excluded_ids = [
            "mcp-the-force||chat_with_gemini25_flash||null-history",
            "mcp-the-force||chat_with_o3||empty-history",
            "mcp-the-force||chat_with_grok4||whitespace-history",
        ]

        for excluded_id in excluded_ids:
            assert excluded_id not in store_ids, (
                f"Session {excluded_id} should be excluded due to empty history. "
                f"This indicates a regression in history filtering."
            )

    def test_non_chat_tools_excluded(self, temp_db):
        """REGRESSION TEST: Ensure non-chat tools are excluded from discovery."""
        config = HistoryStorageConfig(db_path=temp_db)

        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE unified_sessions(
                project TEXT NOT NULL,
                tool TEXT NOT NULL, 
                session_id TEXT NOT NULL,
                history TEXT,
                provider_metadata TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (project, tool, session_id)
            )
        """)

        # Insert non-chat tool sessions that should be excluded
        non_chat_tools = [
            "search_project_history",
            "count_project_tokens",
            "list_sessions",
            "describe_session",
        ]

        for i, tool in enumerate(non_chat_tools):
            conn.execute(
                "INSERT INTO unified_sessions (project, tool, session_id, history, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("mcp-the-force", tool, f"session-{i}", '["content"]', 1234567890 + i),
            )

        conn.commit()
        conn.close()

        stores = config.get_stores_with_types(["conversation"])
        store_ids = [store[1] for store in stores]

        # None of the non-chat tools should appear
        for tool in non_chat_tools:
            tool_stores = [sid for sid in store_ids if f"||{tool}||" in sid]
            assert len(tool_stores) == 0, (
                f"Non-chat tool {tool} should be excluded from conversation stores. "
                f"This indicates a regression in tool filtering."
            )
