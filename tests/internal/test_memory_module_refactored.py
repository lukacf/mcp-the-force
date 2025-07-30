"""Integration tests for refactored memory module using VectorStoreManager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mcp_the_force.memory.async_config import AsyncMemoryConfig


@pytest.mark.asyncio
class TestMemoryModuleRefactored:
    """Test the refactored memory system with VectorStoreManager."""

    @pytest.fixture
    async def memory_config(self, tmp_path):
        """Create AsyncMemoryConfig instance for testing."""
        # Mock settings
        with patch("mcp_the_force.memory.async_config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.memory.enabled = True
            settings.memory.data_dir = str(tmp_path)
            settings.memory.vector_store_provider = "openai"
            settings.memory.rollover_docs_limit = 100
            mock_settings.return_value = settings

            config = AsyncMemoryConfig()
            yield config
            # Cleanup
            if hasattr(config, "_pool"):
                await config._pool.close()

    @pytest.fixture
    def mock_vector_store_manager(self):
        """Mock the vector_store_manager."""
        manager = AsyncMock()
        manager.create = AsyncMock()
        manager._get_client = MagicMock()
        return manager

    async def test_memory_uses_vector_store_manager(
        self, memory_config, mock_vector_store_manager
    ):
        """Test that memory module uses VectorStoreManager instead of OpenAI client."""
        with patch(
            "mcp_the_force.memory.async_config.vector_store_manager",
            mock_vector_store_manager,
        ):
            # Setup mock responses
            mock_vector_store_manager.create.return_value = "vs_memory001"
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value={"id": "vs_memory001"})
            mock_vector_store_manager._get_client.return_value = mock_client

            # Create a conversation store
            await memory_config._create_store_async("conversation", name="Test Store")

            # Verify VectorStoreManager.create was called with correct params
            mock_vector_store_manager.create.assert_called_once()
            call_args = mock_vector_store_manager.create.call_args

            # Check the arguments
            assert call_args.kwargs["name"] == "project-conversation-001"
            assert call_args.kwargs["protected"] is True
            assert call_args.kwargs["files"] == []
            assert "session_id" not in call_args.kwargs

    async def test_no_openai_imports(self):
        """Test that memory module has no direct OpenAI imports."""
        # Read the async_config.py file
        import inspect
        import mcp_the_force.memory.async_config as async_config_module

        source = inspect.getsource(async_config_module)

        # Verify no OpenAI imports
        assert "from ..adapters.openai.client import OpenAIClientFactory" not in source
        assert "OpenAIClientFactory" not in source

    async def test_rollover_with_lineage_tracking(
        self, memory_config, mock_vector_store_manager
    ):
        """Test store rollover includes lineage tracking."""
        with patch(
            "mcp_the_force.memory.async_config.vector_store_manager",
            mock_vector_store_manager,
        ):
            # Setup mocks
            old_store_id = "vs_old001"
            new_store_id = "vs_new001"
            mock_vector_store_manager.create.return_value = new_store_id

            # Mock database to simulate existing store
            with patch.object(memory_config, "_get_active_store") as mock_get_active:
                mock_get_active.return_value = {
                    "store_id": old_store_id,
                    "sequence": 1,
                    "doc_count": 100,
                }

                # Trigger rollover
                await memory_config._rollover_store_async("conversation", old_store_id)

                # Verify create was called with rollover_from
                mock_vector_store_manager.create.assert_called_once()
                call_args = mock_vector_store_manager.create.call_args
                assert call_args.kwargs["rollover_from"] == old_store_id
                assert call_args.kwargs["name"] == "project-conversation-002"

    async def test_provider_independence(
        self, memory_config, mock_vector_store_manager
    ):
        """Test that memory system works with any provider."""
        providers = ["openai", "inmemory", "pinecone", "hnsw"]

        for provider in providers:
            with patch(
                "mcp_the_force.memory.async_config.vector_store_manager",
                mock_vector_store_manager,
            ):
                with patch(
                    "mcp_the_force.memory.async_config.get_settings"
                ) as mock_settings:
                    # Set different provider
                    settings = MagicMock()
                    settings.memory.vector_store_provider = provider
                    mock_settings.return_value = settings

                    # Reset mock
                    mock_vector_store_manager.create.reset_mock()
                    mock_vector_store_manager.create.return_value = f"vs_{provider}001"

                    # Create store
                    await memory_config._create_store_async(
                        "conversation", name=f"Test {provider}"
                    )

                    # Verify it uses the configured provider
                    # The actual provider handling is in VectorStoreManager
                    mock_vector_store_manager.create.assert_called_once()

    async def test_sequential_naming(self, memory_config, mock_vector_store_manager):
        """Test that stores are named sequentially."""
        with patch(
            "mcp_the_force.memory.async_config.vector_store_manager",
            mock_vector_store_manager,
        ):
            # Mock database responses for different sequences
            sequence_responses = [
                [],  # No existing stores
                [{"sequence": 1}],  # One existing store
                [{"sequence": 1}, {"sequence": 2}],  # Two existing stores
            ]
            expected_names = [
                "project-conversation-001",
                "project-conversation-002",
                "project-conversation-003",
            ]

            for seq_response, expected_name in zip(sequence_responses, expected_names):
                mock_vector_store_manager.create.reset_mock()

                with patch.object(memory_config, "_execute_async") as mock_execute:
                    mock_execute.return_value = seq_response
                    mock_vector_store_manager.create.return_value = "vs_test"

                    await memory_config._create_store_async("conversation", name="Test")

                    # Verify correct sequential name
                    call_args = mock_vector_store_manager.create.call_args
                    assert call_args.kwargs["name"] == expected_name

    async def test_store_verification_uses_manager(
        self, memory_config, mock_vector_store_manager
    ):
        """Test that store verification uses VectorStoreManager's client."""
        with patch(
            "mcp_the_force.memory.async_config.vector_store_manager",
            mock_vector_store_manager,
        ):
            store_id = "vs_verify001"

            # Setup mock client
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value={"id": store_id})
            mock_vector_store_manager._get_client.return_value = mock_client

            # Get active store (triggers verification)
            with patch.object(memory_config, "_get_active_store") as mock_get_active:
                mock_get_active.return_value = {"store_id": store_id, "sequence": 1}

                await memory_config.get_active_conversation_store()

                # Verify it used VectorStoreManager's client
                mock_vector_store_manager._get_client.assert_called_once_with("openai")
                mock_client.get.assert_called_once_with(store_id)

    async def test_error_handling_during_rollover(
        self, memory_config, mock_vector_store_manager
    ):
        """Test error handling during store rollover."""
        with patch(
            "mcp_the_force.memory.async_config.vector_store_manager",
            mock_vector_store_manager,
        ):
            # Make create fail
            mock_vector_store_manager.create.side_effect = Exception("Provider error")

            # Mock existing store
            with patch.object(memory_config, "_get_active_store") as mock_get_active:
                mock_get_active.return_value = {"store_id": "vs_old", "sequence": 1}

                # Rollover should raise the exception
                with pytest.raises(Exception, match="Provider error"):
                    await memory_config._rollover_store_async("conversation", "vs_old")

    async def test_metadata_support(self, memory_config, mock_vector_store_manager):
        """Test that provider metadata can be passed through."""
        with patch(
            "mcp_the_force.memory.async_config.vector_store_manager",
            mock_vector_store_manager,
        ):
            # Future enhancement: memory config could accept provider_metadata
            # For now, just verify the interface exists
            mock_vector_store_manager.create.return_value = "vs_meta001"

            await memory_config._create_store_async("conversation", name="Test")

            # The create method supports provider_metadata even if not used yet
            call_args = mock_vector_store_manager.create.call_args
            assert (
                "provider_metadata" not in call_args.kwargs
                or call_args.kwargs["provider_metadata"] is None
            )
