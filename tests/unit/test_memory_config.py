"""Unit tests for memory configuration using SQLite."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import sqlite3

import pytest

from mcp_the_force.history.config import HistoryStorageConfig, get_history_config


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
def mock_client():
    """Mock OpenAI client."""
    client = MagicMock()
    # Mock vector store creation
    store = MagicMock()
    store.id = "vs_test_store_id"
    client.vector_stores.create.return_value = store
    return client


class TestHistoryStorageConfig:
    """Test memory configuration with SQLite."""

    def test_init_creates_database(self, temp_db, mock_client):
        """Test that initialization creates database tables."""
        HistoryStorageConfig(db_path=temp_db)

        # Check tables were created
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "stores" in tables
        assert "history_meta" in tables

    def test_get_active_conversation_store_creates_first(self, temp_db, mock_client):
        """Test creating first conversation store."""
        with patch(
            "mcp_the_force.history.config.HistoryStorageConfig._create_store"
        ) as mock_create:
            mock_create.return_value = "vs_test_store_id"
            config = HistoryStorageConfig(db_path=temp_db)
            store_id = config.get_active_conversation_store()

        assert store_id == "vs_test_store_id"
        mock_create.assert_called_once_with("conversation", 1)

        # Check database state
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT store_id, store_type, is_active FROM stores")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "vs_test_store_id"
        assert row[1] == "conversation"
        assert row[2] == 1

    def test_get_active_commit_store_creates_first(self, temp_db, mock_client):
        """Test creating first commit store."""
        with patch(
            "mcp_the_force.history.config.HistoryStorageConfig._create_store"
        ) as mock_create:
            mock_create.return_value = "vs_test_store_id"
            config = HistoryStorageConfig(db_path=temp_db)
            store_id = config.get_active_commit_store()

        assert store_id == "vs_test_store_id"
        mock_create.assert_called_once_with("commit", 1)

    def test_increment_counts(self, temp_db, mock_client):
        """Test incrementing document counts."""
        with patch(
            "mcp_the_force.history.config.HistoryStorageConfig._create_store"
        ) as mock_create:
            # Mock different store IDs for conversation and commit
            mock_create.side_effect = ["vs_conversation_store", "vs_commit_store"]
            config = HistoryStorageConfig(db_path=temp_db)

            # Create stores first
            config.get_active_conversation_store()
            config.get_active_commit_store()

            # Increment counts
            config.increment_conversation_count()
            config.increment_conversation_count()
            config.increment_commit_count()

        # Check counts in database
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT store_type, doc_count FROM stores WHERE is_active = 1 ORDER BY store_type"
        )
        rows = cursor.fetchall()
        conn.close()

        assert rows[0][0] == "commit"
        assert rows[0][1] == 1
        assert rows[1][0] == "conversation"
        assert rows[1][1] == 2

    def test_rollover_at_limit(self, temp_db, mock_client):
        """Test store rollover when limit is reached."""
        with (
            patch(
                "mcp_the_force.history.config.HistoryStorageConfig._create_store"
            ) as mock_create,
            patch("mcp_the_force.history.config.get_settings") as mock_settings,
        ):
            # Mock different store IDs
            mock_create.side_effect = ["vs_store_001", "vs_store_002"]
            # Set low rollover limit for testing
            settings = MagicMock()
            settings.history_rollover_limit = 2
            settings.session_db_path = str(temp_db)
            mock_settings.return_value = settings

            config = HistoryStorageConfig(db_path=temp_db)

            # Get first store
            store_id1 = config.get_active_conversation_store()
            assert store_id1 == "vs_store_001"

            # Increment to limit
            config.increment_conversation_count()
            config.increment_conversation_count()

            # Next get should trigger rollover
            store_id2 = config.get_active_conversation_store()
            assert store_id2 == "vs_store_002"

            # Check both stores exist in database
            conn = sqlite3.connect(temp_db)
            cursor = conn.execute(
                "SELECT store_id, is_active FROM stores WHERE store_type = 'conversation' ORDER BY store_id"
            )
            rows = cursor.fetchall()
            conn.close()

            assert len(rows) == 2
            assert rows[0][0] == "vs_store_001"
            assert rows[0][1] == 0  # Not active
            assert rows[1][0] == "vs_store_002"
            assert rows[1][1] == 1  # Active

    def test_get_all_store_ids(self, temp_db, mock_client):
        """Test retrieving all store IDs."""
        with patch(
            "mcp_the_force.history.config.HistoryStorageConfig._create_store"
        ) as mock_create:
            # Mock creating multiple stores
            mock_create.side_effect = [f"vs_store_{i:03d}" for i in range(4)]
            config = HistoryStorageConfig(db_path=temp_db)

            # Create some stores
            config.get_active_conversation_store()
            config.get_active_commit_store()

            # Get all IDs
            all_ids = config.get_all_store_ids()

        assert len(all_ids) == 2
        assert "vs_store_000" in all_ids
        assert "vs_store_001" in all_ids

    def test_singleton_instance(self, temp_db, mock_client):
        """Test that get_history_config returns singleton."""
        with patch("mcp_the_force.history.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.session_db_path = str(temp_db)
            settings.history_rollover_limit = 9500
            mock_settings.return_value = settings

            config1 = get_history_config()
            config2 = get_history_config()

        assert config1 is config2

    def test_concurrent_access(self, temp_db):
        """Test concurrent access to the database."""
        import threading
        import uuid

        results = []

        # Create a mock client that generates unique IDs
        def create_mock_client():
            client = MagicMock()

            def create_store(name, expires_after=None):
                store = MagicMock()
                store.id = f"vs_{uuid.uuid4().hex[:8]}"
                return store

            client.vector_stores.create.side_effect = create_store
            return client

        def create_stores(config, store_type):
            """Create stores in a thread."""
            try:
                if store_type == "conversation":
                    store_id = config.get_active_conversation_store()
                    config.increment_conversation_count()
                else:
                    store_id = config.get_active_commit_store()
                    config.increment_commit_count()
                results.append((store_type, store_id))
            except Exception as e:
                results.append((store_type, f"ERROR: {e}"))

        with patch(
            "mcp_the_force.history.config.HistoryStorageConfig._create_store"
        ) as mock_create:
            # Generate unique store IDs for concurrent access
            store_counter = [0]

            def thread_safe_create_store(store_type, store_num):
                with threading.Lock():
                    store_counter[0] += 1
                    return f"vs_{store_type}_{store_counter[0]:03d}"

            mock_create.side_effect = thread_safe_create_store
            config = HistoryStorageConfig(db_path=temp_db)

            # Create threads
            threads = []
            for i in range(5):
                t1 = threading.Thread(
                    target=create_stores, args=(config, "conversation")
                )
                t2 = threading.Thread(target=create_stores, args=(config, "commit"))
                threads.extend([t1, t2])

            # Start all threads
            for t in threads:
                t.start()

            # Wait for completion
            for t in threads:
                t.join()

        # Check results - should have no errors
        errors = [r for r in results if "ERROR" in str(r[1])]
        assert len(errors) == 0, f"Concurrent access errors: {errors}"

        # Check database state
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT COUNT(*) FROM stores")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 2  # One active store per type


class TestForceConversationIntegration:
    """Test Force conversation discovery integration."""

    def test_get_stores_with_types_basic_stores_only(self, temp_db):
        """Test get_stores_with_types with only traditional stores."""
        config = HistoryStorageConfig(db_path=temp_db)

        # Manually insert traditional stores
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("vs_conversation_123", "conversation", 10, "2024-01-01", 1),
        )
        conn.execute(
            "INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("vs_commit_456", "commit", 5, "2024-01-01", 1),
        )
        conn.commit()
        conn.close()

        # Test getting conversation stores
        stores = config.get_stores_with_types(["conversation"])
        assert len(stores) == 1
        assert stores[0] == ("conversation", "vs_conversation_123")

        # Test getting commit stores
        stores = config.get_stores_with_types(["commit"])
        assert len(stores) == 1
        assert stores[0] == ("commit", "vs_commit_456")

        # Test getting both types
        stores = config.get_stores_with_types(["conversation", "commit"])
        assert len(stores) == 2
        store_dict = dict(stores)
        assert store_dict["conversation"] == "vs_conversation_123"
        assert store_dict["commit"] == "vs_commit_456"

    def test_get_stores_with_types_includes_force_conversations(self, temp_db):
        """Test that get_stores_with_types includes Force conversation sessions.

        Uses the CURRENT schema where tool is stored per-message in the
        history JSON, not as a separate column.
        """
        config = HistoryStorageConfig(db_path=temp_db)

        # Add traditional conversation store
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("vs_traditional_conv", "conversation", 10, "2024-01-01", 1),
        )

        # Add unified_sessions table with CURRENT schema (no tool column!)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS unified_sessions(
                project TEXT NOT NULL,
                session_id TEXT NOT NULL,
                history TEXT,
                provider_metadata TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (project, session_id)
            )
        """)

        # Insert Force conversation sessions with tool stored IN the history JSON
        import json

        gemini_history = json.dumps(
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
        )

        gpt_history = json.dumps(
            [
                {
                    "role": "user",
                    "content": "Debug session",
                    "tool": "chat_with_gpt52",
                },
                {
                    "role": "assistant",
                    "content": "Debug response",
                    "tool": "chat_with_gpt52",
                },
            ]
        )

        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (
                "mcp-the-force",
                "memory-vault-diagnostic",
                gemini_history,
                1234567890,
            ),
        )

        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (
                "mcp-the-force",
                "debug-session",
                gpt_history,
                1234567891,
            ),
        )

        # Insert session with no history (should be excluded)
        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("mcp-the-force", "empty-session", None, 1234567892),
        )

        # Insert non-chat tool session (should be excluded)
        non_chat_history = json.dumps(
            [
                {
                    "role": "user",
                    "content": "Search query",
                    "tool": "search_project_history",
                },
                {
                    "role": "assistant",
                    "content": "Search results",
                    "tool": "search_project_history",
                },
            ]
        )
        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (
                "mcp-the-force",
                "search-session",
                non_chat_history,
                1234567893,
            ),
        )

        conn.commit()
        conn.close()

        # Test getting conversation stores - should only include traditional stores (not Force sessions)
        stores = config.get_stores_with_types(["conversation"])
        assert len(stores) == 1, f"Expected 1 store, got {len(stores)}: {stores}"

        store_ids = [store[1] for store in stores]

        # Check traditional store is included
        assert "vs_traditional_conv" in store_ids

        # Verify all entries are marked as conversation type
        for store_type, store_id in stores:
            assert store_type == "conversation"

        # Test getting session stores - should include Force conversation sessions
        stores = config.get_stores_with_types(["session"])
        assert len(stores) == 2, f"Expected 2 stores, got {len(stores)}: {stores}"

        store_ids = [store[1] for store in stores]

        # Check Force conversation sessions are included with correct format
        # Store ID format is now project||session_id (no tool in ID)
        assert "mcp-the-force||memory-vault-diagnostic" in store_ids
        assert "mcp-the-force||debug-session" in store_ids

        # Verify all entries are marked as session type
        for store_type, store_id in stores:
            assert store_type == "session"

    def test_get_stores_with_types_force_conversations_only_when_requested(
        self, temp_db
    ):
        """Test that Force conversations only appear when session type is requested.

        Uses the CURRENT schema where tool is stored per-message in the
        history JSON, not as a separate column.
        """
        import json

        config = HistoryStorageConfig(db_path=temp_db)

        # Add commit store
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("vs_commit_123", "commit", 5, "2024-01-01", 1),
        )

        # Add unified_sessions with CURRENT schema (no tool column!)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS unified_sessions(
                project TEXT NOT NULL,
                session_id TEXT NOT NULL,
                history TEXT,
                provider_metadata TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (project, session_id)
            )
        """)

        # Insert session with tool stored IN the history JSON
        gemini_history = json.dumps(
            [
                {
                    "role": "user",
                    "content": "Test message",
                    "tool": "chat_with_gemini3_pro_preview",
                },
                {
                    "role": "assistant",
                    "content": "Test response",
                    "tool": "chat_with_gemini3_pro_preview",
                },
            ]
        )

        conn.execute(
            "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (
                "mcp-the-force",
                "test-session",
                gemini_history,
                1234567890,
            ),
        )
        conn.commit()
        conn.close()

        # Test getting only commit stores - should not include Force sessions
        stores = config.get_stores_with_types(["commit"])
        assert len(stores) == 1
        assert stores[0] == ("commit", "vs_commit_123")

        # Test getting conversation stores - should NOT include Force sessions
        stores = config.get_stores_with_types(["conversation"])
        assert len(stores) == 0

        # Test getting session stores - should include Force sessions
        stores = config.get_stores_with_types(["session"])
        assert len(stores) == 1
        assert stores[0][0] == "session"
        # Store ID format is now project||session_id (no tool in ID)
        assert stores[0][1] == "mcp-the-force||test-session"

    def test_get_stores_with_types_empty_request(self, temp_db):
        """Test get_stores_with_types with empty store_types list."""
        config = HistoryStorageConfig(db_path=temp_db)

        # Should return empty list for empty request
        stores = config.get_stores_with_types([])
        assert stores == []

    def test_force_conversation_filtering(self, temp_db):
        """Test that Force conversation filtering works correctly.

        Uses the CURRENT schema where tool is stored per-message in the
        history JSON, not as a separate column.
        """
        import json

        config = HistoryStorageConfig(db_path=temp_db)

        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS unified_sessions(
                project TEXT NOT NULL,
                session_id TEXT NOT NULL,
                history TEXT,
                provider_metadata TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (project, session_id)
            )
        """)

        # Helper to create history JSON with tool per-message
        def make_history(tool_name):
            return json.dumps(
                [
                    {"role": "user", "content": "test", "tool": tool_name},
                    {"role": "assistant", "content": "response", "tool": tool_name},
                ]
            )

        # Test cases for filtering (now tool is in history JSON, not column)
        test_cases = [
            # Should be included - chat_with_* tools with valid history
            (
                "mcp-the-force",
                "session1",
                make_history("chat_with_gemini3_flash_preview"),
                True,
            ),
            ("mcp-the-force", "session2", make_history("chat_with_gpt52"), True),
            ("mcp-the-force", "session3", make_history("chat_with_grok41"), True),
            # Should be excluded - empty/null history
            ("mcp-the-force", "empty1", None, False),
            ("mcp-the-force", "empty2", "", False),
            ("mcp-the-force", "empty3", "[]", False),
            # Should be excluded - non chat_with_* tools
            ("mcp-the-force", "search1", make_history("search_project_history"), False),
            ("mcp-the-force", "count1", make_history("count_project_tokens"), False),
            ("mcp-the-force", "list1", make_history("list_sessions"), False),
        ]

        for i, (project, session_id, history, _should_include) in enumerate(test_cases):
            conn.execute(
                "INSERT INTO unified_sessions (project, session_id, history, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (project, session_id, history, 1234567890 + i),
            )

        conn.commit()
        conn.close()

        # Get conversation stores - should be empty (no Force sessions)
        stores = config.get_stores_with_types(["conversation"])
        store_ids = [store[1] for store in stores]
        assert len(store_ids) == 0, f"Expected no conversation stores, got: {store_ids}"

        # Get session stores - should include Force conversation sessions
        stores = config.get_stores_with_types(["session"])
        store_ids = [store[1] for store in stores]

        # Verify expected inclusions (store_id format is project||session_id)
        expected_included = [
            "mcp-the-force||session1",
            "mcp-the-force||session2",
            "mcp-the-force||session3",
        ]

        for expected in expected_included:
            assert (
                expected in store_ids
            ), f"Expected {expected} to be included, got: {store_ids}"

        # Verify expected exclusions
        expected_excluded = [
            "mcp-the-force||empty1",
            "mcp-the-force||empty2",
            "mcp-the-force||empty3",
            "mcp-the-force||search1",
            "mcp-the-force||count1",
            "mcp-the-force||list1",
        ]

        for excluded in expected_excluded:
            assert (
                excluded not in store_ids
            ), f"Expected {excluded} to be excluded, got: {store_ids}"
