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
