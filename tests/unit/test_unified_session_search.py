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
    """Create a database with unified session data.

    Uses the CURRENT schema where tool is stored per-message in the
    history JSON, not as a separate column.
    """
    # Create the tables
    conn = sqlite3.connect(temp_db)

    # Create unified_sessions table with CURRENT schema (no tool column!)
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

    # Insert sample Force conversation sessions with tool stored IN the history JSON
    test_conversations = [
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
            "session_id": "architecture-discussion",
            "history": json.dumps(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Explain the adapter architecture"}
                        ],
                        "tool": "chat_with_grok41",
                    },
                    {
                        "role": "assistant",
                        "content": "The adapter system uses protocol-based design",
                        "tool": "chat_with_grok41",
                    },
                ]
            ),
            "updated_at": 1234567892,
        },
    ]

    for conv in test_conversations:
        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (
                conv["project"],
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

        # Get conversation stores - should only include traditional stores
        stores = config.get_stores_with_types(["conversation"])

        # Should include only traditional store (not Force conversation sessions)
        assert len(stores) == 1

        store_ids = [store[1] for store in stores]
        assert "vs_traditional_store" in store_ids

        # Get session stores - should include Force conversation sessions
        stores = config.get_stores_with_types(["session"])
        assert len(stores) == 3

        # Store ID format is now project||session_id (no tool in ID)
        store_ids = [store[1] for store in stores]
        assert "mcp-the-force||memory-vault-diagnostic" in store_ids
        assert "mcp-the-force||ollama-debug-session" in store_ids
        assert "mcp-the-force||architecture-discussion" in store_ids


class TestRegressionPrevention:
    """Tests to prevent regression of Force conversation discovery."""

    def test_unified_sessions_only_discovered_for_session_searches(self, populated_db):
        """REGRESSION TEST: Ensure unified sessions are only discovered when explicitly searching sessions."""
        config = HistoryStorageConfig(db_path=populated_db)

        # Conversation searches should NOT include Force sessions (unified sessions)
        conversation_stores = config.get_stores_with_types(["conversation"])
        # Unified sessions have "||" in their store_id (project||session_id format)
        unified_session_stores = [
            store for store in conversation_stores if "||" in store[1]
        ]

        # Should find zero unified sessions in conversation search
        assert len(unified_session_stores) == 0, (
            f"Expected no unified sessions in conversation search, got {len(unified_session_stores)}. "
            f"Unified sessions should only appear when explicitly requesting 'session' store type."
        )

        # Session searches should include unified sessions with chat_with_* tools
        session_stores = config.get_stores_with_types(["session"])

        # Must find at least the sessions we inserted that have chat_with_* tools
        assert len(session_stores) >= 3, (
            f"Expected at least 3 sessions in session search, got {len(session_stores)}. "
            f"This indicates a regression in unified session discovery for session searches."
        )

        # Verify the store IDs have correct format (project||session_id)
        for store_type, store_id in session_stores:
            assert store_type == "session"
            parts = store_id.split("||")
            assert (
                len(parts) == 2
            ), f"Invalid store ID format: {store_id}, expected project||session_id"

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
                session_id TEXT NOT NULL,
                history TEXT,
                provider_metadata TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (project, session_id)
            )
        """)

        # Insert sessions that should be excluded (empty/null history)
        excluded_sessions = [
            ("mcp-the-force", "null-history", None),
            ("mcp-the-force", "empty-history", ""),
            ("mcp-the-force", "whitespace-history", "   "),
            ("mcp-the-force", "empty-array", "[]"),
        ]

        for i, (project, session_id, history) in enumerate(excluded_sessions):
            conn.execute(
                "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (project, session_id, history, 1234567890 + i),
            )

        conn.commit()
        conn.close()

        # Get session stores - should exclude all empty history sessions
        stores = config.get_stores_with_types(["session"])
        store_ids = [store[1] for store in stores]

        excluded_ids = [
            "mcp-the-force||null-history",
            "mcp-the-force||empty-history",
            "mcp-the-force||whitespace-history",
            "mcp-the-force||empty-array",
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
                session_id TEXT NOT NULL,
                history TEXT,
                provider_metadata TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (project, session_id)
            )
        """)

        # Insert sessions with non-chat tools in their history (should be excluded)
        non_chat_tools = [
            "search_project_history",
            "count_project_tokens",
            "list_sessions",
            "describe_session",
            "work_with",
        ]

        for i, tool in enumerate(non_chat_tools):
            history = json.dumps(
                [
                    {"role": "user", "content": "test", "tool": tool},
                    {"role": "assistant", "content": "response", "tool": tool},
                ]
            )
            conn.execute(
                "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
                "VALUES (?, ?, ?, ?)",
                ("mcp-the-force", f"session-{tool}", history, 1234567890 + i),
            )

        conn.commit()
        conn.close()

        # Session search should exclude non-chat_with_* tools
        stores = config.get_stores_with_types(["session"])
        store_ids = [store[1] for store in stores]

        # None of the non-chat tools should appear
        assert len(store_ids) == 0, (
            f"Non-chat tool sessions should be excluded from session search. "
            f"Found: {store_ids}. "
            f"This indicates a regression in tool filtering."
        )
