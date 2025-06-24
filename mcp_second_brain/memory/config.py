"""Configuration management for project memory system."""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from ..utils.vector_store import get_client
from ..config import get_settings

logger = logging.getLogger(__name__)


class MemoryConfig:
    """Manages memory store configuration and rollover."""

    def __init__(self, config_path: Optional[Path] = None):
        settings = get_settings()
        self.config_path = config_path or Path(settings.memory_config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load_config()
        self._client = get_client()
        self._lock = threading.RLock()
        self._rollover_limit = settings.memory_rollover_limit

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default."""
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                data = json.load(f)
                assert isinstance(data, dict)
                return data

        # Default configuration
        return {
            "conversation_stores": [],
            "commit_stores": [],
            "active_conv_index": -1,
            "active_commit_index": -1,
            "created_at": datetime.utcnow().isoformat(),
            "last_gc": datetime.utcnow().isoformat(),
        }

    def _save_config(self):
        """Save configuration to file atomically."""
        with self._lock:
            # Write to temp file first
            temp_path = self.config_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(self._config, f, indent=2)
            # Atomic rename
            temp_path.replace(self.config_path)

    def get_active_conversation_store(self) -> str:
        """Get active conversation store ID, creating if needed."""
        with self._lock:
            stores = self._config["conversation_stores"]
            active_index = self._config["active_conv_index"]

            # Create first store if none exist
            if not stores:
                store = self._client.vector_stores.create(
                    name="project-conversations-001"
                )
                stores.append(
                    {
                        "id": store.id,
                        "count": 0,
                        "created": datetime.utcnow().isoformat(),
                    }
                )
                self._config["active_conv_index"] = 0
                self._save_config()
                store_id = store.id
                assert isinstance(store_id, str)
                return store_id

            # Check if active store needs rollover
            active_store = stores[active_index]
            if active_store["count"] >= self._rollover_limit:
                # Create new store
                store_num = len(stores) + 1
                store = self._client.vector_stores.create(
                    name=f"project-conversations-{store_num:03d}"
                )
                stores.append(
                    {
                        "id": store.id,
                        "count": 0,
                        "created": datetime.utcnow().isoformat(),
                    }
                )
                self._config["active_conv_index"] = len(stores) - 1
                self._save_config()
                store_id = store.id
                assert isinstance(store_id, str)
                return store_id

            store_id = active_store["id"]
            assert isinstance(store_id, str)
            return store_id

    def get_active_commit_store(self) -> str:
        """Get active commit store ID, creating if needed."""
        with self._lock:
            stores = self._config["commit_stores"]
            active_index = self._config["active_commit_index"]

            # Create first store if none exist
            if not stores:
                store = self._client.vector_stores.create(name="project-commits-001")
                stores.append(
                    {
                        "id": store.id,
                        "count": 0,
                        "created": datetime.utcnow().isoformat(),
                    }
                )
                self._config["active_commit_index"] = 0
                self._save_config()
                store_id = store.id
                assert isinstance(store_id, str)
                return store_id

            # Check if active store needs rollover
            active_store = stores[active_index]
            if active_store["count"] >= self._rollover_limit:
                # Create new store
                store_num = len(stores) + 1
                store = self._client.vector_stores.create(
                    name=f"project-commits-{store_num:03d}"
                )
                stores.append(
                    {
                        "id": store.id,
                        "count": 0,
                        "created": datetime.utcnow().isoformat(),
                    }
                )
                self._config["active_commit_index"] = len(stores) - 1
                self._save_config()
                store_id = store.id
                assert isinstance(store_id, str)
                return store_id

            store_id = active_store["id"]
            assert isinstance(store_id, str)
            return store_id

    def increment_conversation_count(self):
        """Increment document count for active conversation store."""
        with self._lock:
            if self._config["conversation_stores"]:
                active_index = self._config["active_conv_index"]
                self._config["conversation_stores"][active_index]["count"] += 1
                self._save_config()

    def increment_commit_count(self):
        """Increment document count for active commit store."""
        with self._lock:
            if self._config["commit_stores"]:
                active_index = self._config["active_commit_index"]
                self._config["commit_stores"][active_index]["count"] += 1
                self._save_config()

    def get_all_store_ids(self) -> List[str]:
        """Get all store IDs for querying."""
        with self._lock:
            store_ids = []

            # Add all conversation stores
            for store in self._config.get("conversation_stores", []):
                store_ids.append(store["id"])

            # Add all commit stores
            for store in self._config.get("commit_stores", []):
                store_ids.append(store["id"])

            return store_ids


# Global instance and lock
_memory_config: Optional[MemoryConfig] = None
_memory_config_lock = threading.RLock()


def get_memory_config() -> MemoryConfig:
    """Get or create global memory configuration instance."""
    global _memory_config
    with _memory_config_lock:
        if _memory_config is None:
            _memory_config = MemoryConfig()
        return _memory_config
