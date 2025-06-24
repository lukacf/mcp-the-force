"""Unit tests for memory configuration management."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from mcp_second_brain.memory.config import MemoryConfig


class TestMemoryConfig:
    """Test memory configuration management."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory for config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_client(self):
        """Mock OpenAI client."""
        client = Mock()
        # Mock vector store creation
        store = Mock()
        store.id = "test-store-id"
        client.vector_stores.create.return_value = store
        return client

    @pytest.fixture
    def mock_settings(self):
        """Mock settings with memory configuration."""
        settings = Mock()
        settings.memory_rollover_limit = 100  # Low limit for testing
        settings.memory_config_path = "test/stores.json"
        return settings

    def test_init_creates_config_directory(self, temp_config_dir, mock_client):
        """Test that initialization creates config directory."""
        config_path = temp_config_dir / "memory" / "stores.json"

        with patch(
            "mcp_second_brain.memory.config.get_client", return_value=mock_client
        ):
            config = MemoryConfig(config_path)

        assert config_path.parent.exists()
        assert config._config is not None

    def test_load_default_config(self, temp_config_dir, mock_client):
        """Test loading default configuration."""
        config_path = temp_config_dir / "stores.json"

        with patch(
            "mcp_second_brain.memory.config.get_client", return_value=mock_client
        ):
            config = MemoryConfig(config_path)

        assert config._config["conversation_stores"] == []
        assert config._config["commit_stores"] == []
        assert config._config["active_conv_index"] == -1
        assert config._config["active_commit_index"] == -1
        assert "created_at" in config._config
        assert "last_gc" in config._config

    def test_load_existing_config(self, temp_config_dir, mock_client):
        """Test loading existing configuration."""
        config_path = temp_config_dir / "stores.json"

        # Create existing config
        existing_config = {
            "conversation_stores": [
                {"id": "conv-1", "count": 50, "created": "2024-01-01"}
            ],
            "commit_stores": [{"id": "commit-1", "count": 30, "created": "2024-01-01"}],
            "active_conv_index": 0,
            "active_commit_index": 0,
            "created_at": "2024-01-01",
            "last_gc": "2024-01-01",
        }

        with open(config_path, "w") as f:
            json.dump(existing_config, f)

        with patch(
            "mcp_second_brain.memory.config.get_client", return_value=mock_client
        ):
            config = MemoryConfig(config_path)

        assert len(config._config["conversation_stores"]) == 1
        assert config._config["conversation_stores"][0]["id"] == "conv-1"
        assert config._config["active_conv_index"] == 0

    def test_save_config_atomic(self, temp_config_dir, mock_client):
        """Test atomic config saving."""
        config_path = temp_config_dir / "stores.json"

        with patch(
            "mcp_second_brain.memory.config.get_client", return_value=mock_client
        ):
            config = MemoryConfig(config_path)

            # Modify config
            config._config["test_field"] = "test_value"
            config._save_config()

        # Verify saved config
        with open(config_path) as f:
            saved = json.load(f)

        assert saved["test_field"] == "test_value"
        # Verify temp file doesn't exist
        assert not config_path.with_suffix(".tmp").exists()

    def test_get_active_conversation_store_creates_first(
        self, temp_config_dir, mock_client, mock_settings
    ):
        """Test creating first conversation store."""
        config_path = temp_config_dir / "stores.json"

        with patch(
            "mcp_second_brain.memory.config.get_client", return_value=mock_client
        ):
            with patch(
                "mcp_second_brain.memory.config.get_settings",
                return_value=mock_settings,
            ):
                config = MemoryConfig(config_path)
                store_id = config.get_active_conversation_store()

        assert store_id == "test-store-id"
        assert len(config._config["conversation_stores"]) == 1
        assert config._config["active_conv_index"] == 0
        mock_client.vector_stores.create.assert_called_once_with(
            name="project-conversations-001"
        )

    def test_get_active_conversation_store_rollover(
        self, temp_config_dir, mock_client, mock_settings
    ):
        """Test store rollover when limit reached."""
        config_path = temp_config_dir / "stores.json"

        # Create config with store at limit
        existing_config = {
            "conversation_stores": [
                {"id": "conv-1", "count": 100, "created": "2024-01-01"}
            ],
            "commit_stores": [],
            "active_conv_index": 0,
            "active_commit_index": -1,
            "created_at": "2024-01-01",
            "last_gc": "2024-01-01",
        }

        with open(config_path, "w") as f:
            json.dump(existing_config, f)

        with patch(
            "mcp_second_brain.memory.config.get_client", return_value=mock_client
        ):
            with patch(
                "mcp_second_brain.memory.config.get_settings",
                return_value=mock_settings,
            ):
                config = MemoryConfig(config_path)
                store_id = config.get_active_conversation_store()

        assert store_id == "test-store-id"
        assert len(config._config["conversation_stores"]) == 2
        assert config._config["active_conv_index"] == 1
        mock_client.vector_stores.create.assert_called_once_with(
            name="project-conversations-002"
        )

    def test_increment_counts(self, temp_config_dir, mock_client):
        """Test incrementing document counts."""
        config_path = temp_config_dir / "stores.json"

        # Create config with existing stores
        existing_config = {
            "conversation_stores": [
                {"id": "conv-1", "count": 10, "created": "2024-01-01"}
            ],
            "commit_stores": [{"id": "commit-1", "count": 5, "created": "2024-01-01"}],
            "active_conv_index": 0,
            "active_commit_index": 0,
            "created_at": "2024-01-01",
            "last_gc": "2024-01-01",
        }

        with open(config_path, "w") as f:
            json.dump(existing_config, f)

        with patch(
            "mcp_second_brain.memory.config.get_client", return_value=mock_client
        ):
            config = MemoryConfig(config_path)

            # Increment counts
            config.increment_conversation_count()
            config.increment_commit_count()

        assert config._config["conversation_stores"][0]["count"] == 11
        assert config._config["commit_stores"][0]["count"] == 6

    def test_get_all_store_ids(self, temp_config_dir, mock_client):
        """Test getting all store IDs."""
        config_path = temp_config_dir / "stores.json"

        # Create config with multiple stores
        existing_config = {
            "conversation_stores": [
                {"id": "conv-1", "count": 10, "created": "2024-01-01"},
                {"id": "conv-2", "count": 20, "created": "2024-01-02"},
            ],
            "commit_stores": [{"id": "commit-1", "count": 5, "created": "2024-01-01"}],
            "active_conv_index": 1,
            "active_commit_index": 0,
            "created_at": "2024-01-01",
            "last_gc": "2024-01-01",
        }

        with open(config_path, "w") as f:
            json.dump(existing_config, f)

        with patch(
            "mcp_second_brain.memory.config.get_client", return_value=mock_client
        ):
            config = MemoryConfig(config_path)
            store_ids = config.get_all_store_ids()

        assert len(store_ids) == 3
        assert "conv-1" in store_ids
        assert "conv-2" in store_ids
        assert "commit-1" in store_ids

    def test_thread_safety(self, temp_config_dir, mock_client):
        """Test thread-safe operations."""
        import threading

        config_path = temp_config_dir / "stores.json"

        with patch(
            "mcp_second_brain.memory.config.get_client", return_value=mock_client
        ):
            config = MemoryConfig(config_path)

            # Simulate concurrent access
            results = []

            def get_store():
                store_id = config.get_active_conversation_store()
                results.append(store_id)

            threads = [threading.Thread(target=get_store) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # All threads should get the same store ID
        assert len(set(results)) == 1
        assert results[0] == "test-store-id"

    def test_get_memory_config_singleton(self, mock_client):
        """Test that get_memory_config returns singleton."""
        from mcp_second_brain.memory.config import get_memory_config

        # Clear any existing instance
        import mcp_second_brain.memory.config

        mcp_second_brain.memory.config._memory_config = None

        with patch(
            "mcp_second_brain.memory.config.get_client", return_value=mock_client
        ):
            config1 = get_memory_config()
            config2 = get_memory_config()

        assert config1 is config2
