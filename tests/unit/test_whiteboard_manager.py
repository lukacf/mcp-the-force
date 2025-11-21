"""Tests for WhiteboardManager - the vector store collaboration backend."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from mcp_the_force.local_services.whiteboard_manager import WhiteboardManager
from mcp_the_force.types.collaboration import CollaborationMessage


@pytest.fixture
def mock_vector_store_manager():
    """Mock VectorStoreManager for testing."""
    manager = Mock()
    manager.create = AsyncMock()
    manager.renew_lease = AsyncMock()
    manager.delete = AsyncMock()
    # Mock the vector_store_cache attribute
    manager.vector_store_cache = Mock()
    manager.vector_store_cache.get_store = Mock()
    manager.vector_store_cache.set_inactive = AsyncMock()
    return manager


@pytest.fixture
def mock_unified_session_cache():
    """Mock UnifiedSessionCache for testing."""
    cache = Mock()
    cache.get_metadata = AsyncMock()
    cache.set_metadata = AsyncMock()
    return cache


@pytest.fixture
def whiteboard_manager(mock_vector_store_manager, mock_unified_session_cache):
    """WhiteboardManager instance with mocked dependencies."""
    return WhiteboardManager(mock_vector_store_manager, mock_unified_session_cache)


class TestWhiteboardManagerCreation:
    """Test whiteboard vector store creation."""

    @pytest.mark.asyncio
    async def test_create_whiteboard_openai_first(
        self, whiteboard_manager, mock_vector_store_manager
    ):
        """Test whiteboard tries OpenAI first, returns store_id and provider."""

        # Mock successful OpenAI store creation
        mock_vector_store_manager.create.return_value = {
            "store_id": "vs_openai_123",
            "provider": "openai",
        }

        result = await whiteboard_manager.create_whiteboard("test-session-123")

        # Verify OpenAI was tried first
        mock_vector_store_manager.create.assert_called_once()
        call_args = mock_vector_store_manager.create.call_args
        assert call_args.kwargs["provider"] == "openai"
        assert call_args.kwargs["session_id"] == "collab_test-session-123"

        # Verify correct return format
        assert result == {"store_id": "vs_openai_123", "provider": "openai"}

    @pytest.mark.asyncio
    async def test_create_whiteboard_fallback_to_hnsw(
        self, whiteboard_manager, mock_vector_store_manager
    ):
        """Test fallback to HNSW when OpenAI unavailable."""

        # Mock OpenAI failure then HNSW success
        def mock_create(*args, **kwargs):
            if kwargs.get("provider") == "openai":
                raise Exception("OpenAI quota exceeded")
            return {"store_id": "vs_hnsw_456", "provider": "hnsw"}

        mock_vector_store_manager.create.side_effect = mock_create

        result = await whiteboard_manager.create_whiteboard("test-session-456")

        # Should have tried twice (OpenAI then HNSW)
        assert mock_vector_store_manager.create.call_count == 2

        # Verify final result uses HNSW
        assert result == {"store_id": "vs_hnsw_456", "provider": "hnsw"}

    @pytest.mark.asyncio
    async def test_create_whiteboard_stores_metadata(
        self, whiteboard_manager, mock_unified_session_cache
    ):
        """Test that store info is saved to session metadata."""

        # Mock successful creation
        whiteboard_manager.vs_manager.create = AsyncMock(
            return_value={"store_id": "vs_test_789", "provider": "openai"}
        )

        await whiteboard_manager.create_whiteboard("metadata-test")

        # Verify metadata was stored with project parameter
        mock_unified_session_cache.set_metadata.assert_called_once_with(
            "mcp-the-force",  # project name
            "group_think",  # tool
            "metadata-test",  # session_id
            "whiteboard",  # key
            {"store_id": "vs_test_789", "provider": "openai"},  # value
        )


class TestWhiteboardManagerMessages:
    """Test message storage and retrieval."""

    @pytest.mark.asyncio
    async def test_append_message_creates_vsfile(self, whiteboard_manager):
        """Test message stored as VSFile with correct path pattern."""

        # Setup: Mock existing store info and sequence counter
        store_info = {"store_id": "vs_test_123", "provider": "openai"}

        async def mock_get_metadata(project, tool, session_id, key):
            if key == "whiteboard":
                return store_info
            elif key == "whiteboard_seq":
                return None  # No existing sequence
            else:
                return None

        whiteboard_manager.session_cache.get_metadata = AsyncMock(
            side_effect=mock_get_metadata
        )

        # Mock VSFile addition with new API
        mock_store = AsyncMock()
        mock_store.add_files = AsyncMock()

        mock_client = Mock()
        mock_client.get = AsyncMock(return_value=mock_store)
        whiteboard_manager.vs_manager._get_client_for_store = Mock(
            return_value=mock_client
        )

        message = CollaborationMessage(
            speaker="user",
            content="Hello collaboration world!",
            timestamp=datetime.now(),
            metadata={"step": 1},
        )

        await whiteboard_manager.append_message("test-session", message)

        # Verify VSFile was created with correct pattern
        mock_store.add_files.assert_called_once()
        vsfiles = mock_store.add_files.call_args[0][0]  # First positional arg
        assert len(vsfiles) == 1

        vsfile = vsfiles[0]
        # Check path pattern: whiteboard/{session_id}/{idx:04d}_{speaker}.txt
        assert vsfile.path.startswith("whiteboard/test-session/")
        assert vsfile.path.endswith("_user.txt")
        assert "Hello collaboration world!" in vsfile.content

    @pytest.mark.asyncio
    async def test_append_message_increments_index(self, whiteboard_manager):
        """Test message index increments correctly."""

        store_info = {"store_id": "vs_test", "provider": "hnsw"}

        call_count = [0]  # Counter for sequence

        async def mock_get_metadata(project, tool, session_id, key):
            if key == "whiteboard":
                return store_info
            elif key == "whiteboard_seq":
                return call_count[0]  # Return current counter
            else:
                return None

        async def mock_set_metadata(project, tool, session_id, key, value):
            if key == "whiteboard_seq":
                call_count[0] = value  # Update counter

        whiteboard_manager.session_cache.get_metadata = AsyncMock(
            side_effect=mock_get_metadata
        )
        whiteboard_manager.session_cache.set_metadata = AsyncMock(
            side_effect=mock_set_metadata
        )

        # Mock VSFile addition with new API
        mock_store = AsyncMock()
        mock_store.add_files = AsyncMock()

        mock_client = Mock()
        mock_client.get = AsyncMock(return_value=mock_store)
        whiteboard_manager.vs_manager._get_client_for_store = Mock(
            return_value=mock_client
        )

        # Add first message
        msg1 = CollaborationMessage("user", "First message", datetime.now())
        await whiteboard_manager.append_message("index-test", msg1)

        # Add second message
        msg2 = CollaborationMessage("chat_with_gpt5", "Second message", datetime.now())
        await whiteboard_manager.append_message("index-test", msg2)

        # Verify path indices
        assert mock_store.add_files.call_count == 2

        # First call - should be 0001
        first_call_vsfile = mock_store.add_files.call_args_list[0][0][0][0]
        assert "0001_user.txt" in first_call_vsfile.path

        # Second call - should be 0002
        second_call_vsfile = mock_store.add_files.call_args_list[1][0][0][0]
        assert "0002_chat_with_gpt5.txt" in second_call_vsfile.path

    @pytest.mark.asyncio
    async def test_append_message_includes_metadata(self, whiteboard_manager):
        """Test VSFile includes message metadata."""

        store_info = {"store_id": "vs_meta", "provider": "openai"}

        async def mock_get_metadata(project, tool, session_id, key):
            if key == "whiteboard":
                return store_info
            elif key == "whiteboard_seq":
                return None  # No existing sequence
            else:
                return None

        whiteboard_manager.session_cache.get_metadata = AsyncMock(
            side_effect=mock_get_metadata
        )

        # Mock VSFile addition with new API
        mock_store = AsyncMock()
        mock_store.add_files = AsyncMock()

        mock_client = Mock()
        mock_client.get = AsyncMock(return_value=mock_store)
        whiteboard_manager.vs_manager._get_client_for_store = Mock(
            return_value=mock_client
        )

        message = CollaborationMessage(
            speaker="chat_with_gemini25_pro",
            content="Gemini response",
            timestamp=datetime.now(),
            metadata={"model": "gemini-2.5-pro", "turn": 3, "reasoning_effort": "high"},
        )

        await whiteboard_manager.append_message("meta-test", message)

        vsfile = mock_store.add_files.call_args[0][0][0]

        # Check VSFile metadata includes message metadata
        assert vsfile.metadata["speaker"] == "chat_with_gemini25_pro"
        assert vsfile.metadata["model"] == "gemini-2.5-pro"
        assert vsfile.metadata["turn"] == 3
        assert vsfile.metadata["reasoning_effort"] == "high"


class TestWhiteboardManagerStoreInfo:
    """Test store info retrieval and management."""

    @pytest.mark.asyncio
    async def test_get_store_info_from_session_metadata(
        self, whiteboard_manager, mock_unified_session_cache
    ):
        """Test store info retrieval from UnifiedSessionCache metadata."""

        # Mock metadata return
        expected_info = {"store_id": "vs_stored_123", "provider": "hnsw"}
        mock_unified_session_cache.get_metadata.return_value = expected_info

        result = await whiteboard_manager.get_store_info("stored-session")

        # Verify correct metadata key was requested with project parameter
        mock_unified_session_cache.get_metadata.assert_called_once_with(
            "mcp-the-force",  # project
            "group_think",  # tool
            "stored-session",  # session_id
            "whiteboard",  # key
        )

        assert result == expected_info

    @pytest.mark.asyncio
    async def test_get_store_info_returns_none_if_missing(
        self, whiteboard_manager, mock_unified_session_cache
    ):
        """Test returns None if no store info exists."""

        mock_unified_session_cache.get_metadata.return_value = None

        result = await whiteboard_manager.get_store_info("missing-session")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_store_reuses_existing(self, whiteboard_manager):
        """Test get_or_create reuses existing store."""

        # Mock existing store info
        existing_info = {"store_id": "vs_existing", "provider": "openai"}
        whiteboard_manager.session_cache.get_metadata = AsyncMock(
            return_value=existing_info
        )

        result = await whiteboard_manager.get_or_create_store("reuse-session")

        # Should return existing without calling create
        assert result == existing_info
        whiteboard_manager.vs_manager.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_create_store_creates_new(self, whiteboard_manager):
        """Test get_or_create creates new store when none exists."""

        # Mock no existing store
        whiteboard_manager.session_cache.get_metadata = AsyncMock(return_value=None)

        # Mock successful creation
        new_info = {"store_id": "vs_new_created", "provider": "hnsw"}
        whiteboard_manager.vs_manager.create = AsyncMock(return_value=new_info)

        result = await whiteboard_manager.get_or_create_store("new-session")

        # Should have created new store
        whiteboard_manager.vs_manager.create.assert_called_once()
        assert result == new_info


class TestWhiteboardManagerSummarization:
    """Test summarization and rollover functionality."""

    @pytest.mark.asyncio
    async def test_summarize_and_rollover_new_store(self, whiteboard_manager):
        """Test rollover creates new store (HNSW can't delete files)."""

        # Mock current store info and session state
        old_store_info = {"store_id": "vs_old_full", "provider": "hnsw"}
        session_state = {
            "messages": [
                {
                    "speaker": f"user_{i}",
                    "content": f"msg {i}",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {},
                }
                for i in range(60)
            ]  # Over threshold
        }

        async def mock_get_metadata(project, tool, session_id, key):
            if key == "whiteboard":
                return old_store_info
            elif key == "collab_state":
                return session_state
            else:
                return None

        whiteboard_manager.session_cache.get_metadata = AsyncMock(
            side_effect=mock_get_metadata
        )

        # Mock summarization service
        with patch(
            "mcp_the_force.local_services.describe_session.DescribeSessionService"
        ) as mock_describe:
            mock_describe.return_value.execute = AsyncMock(
                return_value="Collaboration summary"
            )

            # Mock new store creation
            new_store_info = {"store_id": "vs_new_rolled", "provider": "hnsw"}
            whiteboard_manager.vs_manager.create = AsyncMock(
                return_value=new_store_info
            )

            # Mock the new store's add_files method with new API
            mock_new_store = AsyncMock()
            mock_new_store.add_files = AsyncMock()

            mock_client = Mock()
            mock_client.get = AsyncMock(return_value=mock_new_store)
            whiteboard_manager.vs_manager._get_client_for_store = Mock(
                return_value=mock_client
            )

            await whiteboard_manager.summarize_and_rollover(
                "rollover-test", threshold=50
            )

            # Verify old store marked inactive
            whiteboard_manager.vs_manager.vector_store_cache.set_inactive.assert_called_once_with(
                "vs_old_full"
            )

            # Verify new store created
            whiteboard_manager.vs_manager.create.assert_called_once()

            # Verify new store info saved to metadata with project parameter
            # Note: set_metadata may be called multiple times, so check if our call exists
            calls = whiteboard_manager.session_cache.set_metadata.call_args_list
            expected_call = (
                "mcp-the-force",  # project
                "group_think",  # tool
                "rollover-test",  # session_id
                "whiteboard",  # key
                new_store_info,  # value
            )
            assert any(
                call[0] == expected_call for call in calls
            ), f"Expected call {expected_call} not found in {[call[0] for call in calls]}"

    @pytest.mark.asyncio
    async def test_summarize_skipped_under_threshold(self, whiteboard_manager):
        """Test summarization skipped when under threshold."""

        store_info = {"store_id": "vs_small", "provider": "openai"}
        whiteboard_manager.session_cache.get_metadata = AsyncMock(
            return_value=store_info
        )

        # Mock session with few messages (under threshold)
        mock_session = Mock()
        mock_session.messages = [Mock() for _ in range(10)]  # Under threshold of 50
        whiteboard_manager.session_cache.get_session = AsyncMock(
            return_value=mock_session
        )

        await whiteboard_manager.summarize_and_rollover("small-test", threshold=50)

        # Should not have created new store or marked old inactive
        whiteboard_manager.vs_manager.create.assert_not_called()
        whiteboard_manager.vs_manager.vector_store_cache.set_inactive.assert_not_called()


class TestWhiteboardManagerErrors:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_append_message_handles_missing_store(self, whiteboard_manager):
        """Test graceful handling when store info is missing."""

        # Mock no store info found
        whiteboard_manager.session_cache.get_metadata = AsyncMock(return_value=None)

        message = CollaborationMessage("user", "test", datetime.now())

        with pytest.raises(ValueError, match="No whiteboard store found"):
            await whiteboard_manager.append_message("missing-store", message)

    @pytest.mark.asyncio
    async def test_create_whiteboard_both_providers_fail(
        self, whiteboard_manager, mock_vector_store_manager
    ):
        """Test error when both OpenAI and HNSW fail."""

        # Mock both providers failing
        mock_vector_store_manager.create.side_effect = Exception("All providers failed")

        with pytest.raises(Exception, match="All providers failed"):
            await whiteboard_manager.create_whiteboard("fail-test")

    @pytest.mark.asyncio
    async def test_renew_lease_called(
        self, whiteboard_manager, mock_vector_store_manager
    ):
        """Test that lease renewal is called during operations."""

        # Mock store exists and sequence counter
        store_info = {"store_id": "vs_lease_test", "provider": "openai"}

        async def mock_get_metadata(project, tool, session_id, key):
            if key == "whiteboard":
                return store_info
            elif key == "whiteboard_seq":
                return None  # No existing sequence
            else:
                return None

        whiteboard_manager.session_cache.get_metadata = AsyncMock(
            side_effect=mock_get_metadata
        )

        # Mock VSFile addition with new API
        mock_store = AsyncMock()
        mock_store.add_files = AsyncMock()

        mock_client = Mock()
        mock_client.get = AsyncMock(return_value=mock_store)
        whiteboard_manager.vs_manager._get_client_for_store = Mock(
            return_value=mock_client
        )

        message = CollaborationMessage("user", "test lease", datetime.now())
        await whiteboard_manager.append_message("lease-test", message)

        # Verify lease renewal was called
        mock_vector_store_manager.renew_lease.assert_called_once_with(
            "collab_lease-test"
        )
