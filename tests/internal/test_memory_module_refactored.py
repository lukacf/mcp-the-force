"""Integration tests for refactored memory module using VectorStoreManager."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
class TestMemoryModuleRefactored:
    """Test the refactored memory system with VectorStoreManager."""

    @pytest.fixture
    async def isolate_test_databases(self, tmp_path):
        """Isolate test databases."""
        # This fixture ensures each test gets a clean database
        yield tmp_path

    async def test_no_openai_imports(self):
        """Test that memory module has no direct OpenAI imports."""
        # Read the async_config.py file
        import inspect
        import mcp_the_force.history.async_config as async_config_module

        source = inspect.getsource(async_config_module)

        # Verify no OpenAI imports
        assert "from ..adapters.openai.client import OpenAIClientFactory" not in source
        assert "OpenAIClientFactory" not in source

    async def test_create_first_conversation_store(self, isolate_test_databases):
        """
        Test that get_active_conversation_store creates a new store
        when no active store exists.
        """
        # 1. Mock the VectorStoreManager dependency at the module level where it's used
        with patch(
            "mcp_the_force.history.async_config.vector_store_manager",
            new_callable=AsyncMock,
        ) as mock_vsm:
            # Configure the mock to return a predictable value
            mock_vsm.create.return_value = {"store_id": "vs_new_conversation_store"}
            mock_vsm.provider = "openai"
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                return_value={"id": "vs_new_conversation_store"}
            )
            mock_vsm._get_client.return_value = mock_client

            # Import the class AFTER mocking is set up
            from mcp_the_force.history.async_config import AsyncHistoryStorageConfig

            # 2. Arrange: Instantiate the class. The DB will be empty.
            memory_config = AsyncHistoryStorageConfig(
                db_path=isolate_test_databases / "memory.db"
            )

            # 3. Act: Call the public method
            store_id = await memory_config.get_active_conversation_store()

            # 4. Assert
            # It should have returned the ID from our mock
            assert store_id == "vs_new_conversation_store"

            # It should have called the manager's create method exactly once
            mock_vsm.create.assert_called_once()

            # Verify it was called with the correct parameters for a new memory store
            call_args = mock_vsm.create.call_args
            assert call_args.kwargs["name"] == "project-conversations-001"
            assert call_args.kwargs["protected"] is True
            assert call_args.kwargs["files"] == []

    async def test_rollover_store_on_limit(self, isolate_test_databases):
        """
        Test that a new store is created when the active one is full.
        """
        with patch(
            "mcp_the_force.history.async_config.vector_store_manager",
            new_callable=AsyncMock,
        ) as mock_vsm:
            # Configure the mock to return the new store's ID
            mock_vsm.create.return_value = {"store_id": "vs_rollover_store"}
            mock_vsm.provider = "openai"

            from mcp_the_force.history.async_config import AsyncHistoryStorageConfig

            # Arrange:
            # - Instantiate the config
            # - Manually set the state of the DB to have one full, active store
            memory_config = AsyncHistoryStorageConfig(
                db_path=isolate_test_databases / "memory.db"
            )

            # Directly manipulate the sync config's DB for setup
            db_conn = memory_config._sync_config._db
            with db_conn:
                # Create a "full" active store
                db_conn.execute(
                    "INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active) VALUES (?, ?, ?, ?, ?)",
                    (
                        "vs_full_store_001",
                        "conversation",
                        10000,
                        1234567890,
                        1,
                    ),  # Set doc_count to rollover_limit
                )

            # Act: This call should trigger a rollover
            new_store_id = await memory_config.get_active_conversation_store()

            # Assert:
            assert new_store_id == "vs_rollover_store"

            # The manager should have been called to create the new store
            mock_vsm.create.assert_called_once()

            # Check that it was called with the correct rollover name and params
            call_args = mock_vsm.create.call_args
            assert call_args.kwargs["name"] == "project-conversations-002"
            assert call_args.kwargs["protected"] is True
            assert call_args.kwargs["rollover_from"] == "vs_full_store_001"

            # Verify the old store is now inactive in the DB
            with db_conn:
                cursor = db_conn.execute(
                    "SELECT is_active FROM stores WHERE store_id = ?",
                    ("vs_full_store_001",),
                )
                row = cursor.fetchone()
                assert row[0] == 0  # is_active should be 0

    async def test_uses_existing_active_store(self, isolate_test_databases):
        """
        Test that an existing, non-full, active store is reused.
        """
        # Mock only the parts of the manager we need to control for this test
        with patch(
            "mcp_the_force.history.async_config.vector_store_manager.create",
            new_callable=AsyncMock,
        ) as mock_create:
            with patch(
                "mcp_the_force.history.async_config.vector_store_manager._get_client"
            ) as mock_get_client:
                with patch(
                    "mcp_the_force.history.async_config.vector_store_manager.provider",
                    "openai",
                ):
                    # Mock the provider's 'get' method to simulate successful verification
                    mock_provider_client = AsyncMock()
                    mock_get_client.return_value = mock_provider_client

                    from mcp_the_force.history.async_config import (
                        AsyncHistoryStorageConfig,
                    )

                    # Arrange:
                    # - Create a store entry that is active but NOT full
                    memory_config = AsyncHistoryStorageConfig(
                        db_path=isolate_test_databases / "memory.db"
                    )
                    db_conn = memory_config._sync_config._db
                    with db_conn:
                        db_conn.execute(
                            "INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active) VALUES (?, ?, ?, ?, ?)",
                            ("vs_existing_store", "conversation", 100, 1234567890, 1),
                        )

                    # Act
                    store_id = await memory_config.get_active_conversation_store()

                    # Assert
                    assert store_id == "vs_existing_store"

                    # The provider client should have been used to verify the store exists
                    mock_provider_client.get.assert_called_once_with(
                        "vs_existing_store"
                    )

                    # Most importantly, no new store should have been created
                    mock_create.assert_not_called()

    async def test_error_handling_during_rollover(self, isolate_test_databases):
        """Test error handling during store rollover."""
        with patch(
            "mcp_the_force.history.async_config.vector_store_manager",
            new_callable=AsyncMock,
        ) as mock_vsm:
            # Make create fail
            mock_vsm.create.side_effect = Exception("Provider error")
            mock_vsm.provider = "openai"

            from mcp_the_force.history.async_config import AsyncHistoryStorageConfig

            # Arrange: Create a full store that would trigger rollover
            memory_config = AsyncHistoryStorageConfig(
                db_path=isolate_test_databases / "memory.db"
            )

            db_conn = memory_config._sync_config._db
            with db_conn:
                # Create a "full" active store
                db_conn.execute(
                    "INSERT INTO stores (store_id, store_type, doc_count, created_at, is_active) VALUES (?, ?, ?, ?, ?)",
                    ("vs_full_store", "conversation", 10000, 1234567890, 1),
                )

            # Act & Assert: Should raise the exception
            with pytest.raises(Exception, match="Provider error"):
                await memory_config.get_active_conversation_store()

    async def test_provider_independence(self, isolate_test_databases):
        """Test that memory system works with any provider through VectorStoreManager."""
        providers = ["openai", "inmemory", "pinecone", "hnsw"]

        for provider in providers:
            with patch(
                "mcp_the_force.history.async_config.vector_store_manager",
                new_callable=AsyncMock,
            ) as mock_vsm:
                # Configure mock for this provider
                mock_vsm.create.return_value = {"store_id": f"vs_{provider}001"}
                mock_vsm.provider = provider

                from mcp_the_force.history.async_config import AsyncHistoryStorageConfig

                # Each provider gets its own DB to avoid conflicts
                memory_config = AsyncHistoryStorageConfig(
                    db_path=isolate_test_databases / f"memory_{provider}.db"
                )

                # Create store
                store_id = await memory_config.get_active_conversation_store()

                # Verify it uses VectorStoreManager regardless of provider
                assert store_id == f"vs_{provider}001"
                mock_vsm.create.assert_called_once()
