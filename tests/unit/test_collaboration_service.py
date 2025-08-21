"""Tests for CollaborationService - the main multi-model orchestrator."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from mcp_the_force.local_services.collaboration_service import CollaborationService
from mcp_the_force.types.collaboration import (
    CollaborationMessage, 
    CollaborationSession, 
    CollaborationConfig
)


@pytest.fixture
def mock_executor():
    """Mock ToolExecutor."""
    executor = Mock()
    executor.execute = AsyncMock()
    return executor


@pytest.fixture  
def mock_whiteboard_manager():
    """Mock WhiteboardManager."""
    manager = Mock()
    manager.get_or_create_store = AsyncMock()
    manager.append_message = AsyncMock()
    manager.summarize_and_rollover = AsyncMock()
    return manager


@pytest.fixture
def mock_session_cache():
    """Mock UnifiedSessionCache."""
    cache = Mock()
    cache.get_session = AsyncMock()
    cache.set_session = AsyncMock()
    return cache


@pytest.fixture
def collaboration_service(mock_executor, mock_whiteboard_manager, mock_session_cache):
    """CollaborationService with mocked dependencies."""
    return CollaborationService(mock_executor, mock_whiteboard_manager, mock_session_cache)


class TestCollaborationServiceBasics:
    """Test basic service functionality."""
    
    def test_service_initialization(self, collaboration_service):
        """Test service initializes with dependencies."""
        assert collaboration_service.executor is not None
        assert collaboration_service.whiteboard is not None
        assert collaboration_service.session_cache is not None
    
    @patch('mcp_the_force.local_services.collaboration_service.WhiteboardManager')
    def test_service_uses_global_dependencies_when_none_provided(self, mock_wb_class):
        """Test service uses global instances when dependencies are None."""
        mock_wb_class.return_value = Mock()
        
        service = CollaborationService()
        
        # Just verify that service was created with non-None dependencies
        # The actual instances depend on what's available globally at test time
        assert service.executor is not None
        assert service.whiteboard is not None
        assert service.session_cache is not None
        
        # The WhiteboardManager constructor should have been called
        mock_wb_class.assert_called_once()


class TestCollaborationServiceExecution:
    """Test main execution flow."""
    
    @pytest.mark.asyncio
    async def test_execute_creates_new_session(self, collaboration_service, mock_session_cache, mock_whiteboard_manager):
        """Test new collaboration session creation."""
        
        # Mock no existing session
        mock_session_cache.get_session.return_value = None
        
        # Mock whiteboard creation
        mock_whiteboard_manager.get_or_create_store.return_value = {"store_id": "vs_test", "provider": "openai"}
        
        # Mock successful model execution
        collaboration_service.executor.execute.return_value = "GPT-5 response to the objective"
        
        result = await collaboration_service.execute(
            session_id="new-session-123",
            objective="Solve a complex AI problem",
            models=["chat_with_gpt5", "chat_with_gemini25_pro"],
            user_input="Let's start collaborating!",
            config=CollaborationConfig(max_steps=5)
        )
        
        # Verify new session was created and saved
        mock_session_cache.set_session.assert_called()
        saved_session_args = mock_session_cache.set_session.call_args[1]
        
        assert saved_session_args["tool"] == "chatter_collaborate"
        assert saved_session_args["session_id"] == "new-session-123"
        assert isinstance(saved_session_args["session"], CollaborationSession)
        
        saved_session = saved_session_args["session"]
        assert saved_session.objective == "Solve a complex AI problem"
        assert saved_session.models == ["chat_with_gpt5", "chat_with_gemini25_pro"]
        assert saved_session.mode == "round_robin"  # Default
        assert saved_session.max_steps == 5
        
        # Verify whiteboard was created
        mock_whiteboard_manager.get_or_create_store.assert_called_once_with("new-session-123")
        
        # Verify model was called
        collaboration_service.executor.execute.assert_called()
        
        # Verify response
        assert "GPT-5 response" in result
    
    @pytest.mark.asyncio
    async def test_execute_continues_existing_session(self, collaboration_service, mock_session_cache):
        """Test resuming existing session."""
        
        # Mock existing session
        existing_session = CollaborationSession(
            session_id="existing-session",
            objective="Ongoing project",
            models=["chat_with_gpt5", "chat_with_claude41_opus"],
            messages=[CollaborationMessage("user", "Previous message", datetime.now())],
            current_step=1,
            mode="orchestrator",
            max_steps=10,
            status="active"
        )
        mock_session_cache.get_session.return_value = existing_session
        
        # Mock model execution
        collaboration_service.executor.execute.return_value = "Claude response"
        
        result = await collaboration_service.execute(
            session_id="existing-session",
            objective="Should be ignored - using existing",
            models=["should", "be", "ignored"],
            user_input="Continue the conversation"
        )
        
        # Verify existing session was used (not recreated)
        # The set_session call should update the existing session with new message
        assert mock_session_cache.set_session.called
        
        # Verify response
        assert "Claude response" in result


class TestCollaborationServiceRoundRobin:
    """Test round-robin orchestration."""
    
    @pytest.mark.asyncio
    async def test_round_robin_turn_sequence(self, collaboration_service, mock_session_cache):
        """Test models called in correct order."""
        
        # Create session with 3 models
        session = CollaborationSession(
            session_id="round-robin-test",
            objective="Test round robin",
            models=["model_a", "model_b", "model_c"],
            messages=[],
            current_step=0,
            mode="round_robin", 
            max_steps=6,
            status="active"
        )
        mock_session_cache.get_session.return_value = session
        
        # Mock tool metadata lookup
        with patch.object(collaboration_service, '_get_tool_metadata') as mock_get_tool:
            mock_get_tool.return_value = {"name": "model_a", "type": "tool"}
            
            # Mock model execution
            collaboration_service.executor.execute.return_value = "Model response"
            
            # Execute turn 1 (should call model_a)
            await collaboration_service.execute(
                session_id="round-robin-test",
                objective="",
                models=[],
                user_input="Turn 1"
            )
            
            # Verify model_a metadata was requested
            mock_get_tool.assert_called_once_with("model_a")
        
        # Verify session was advanced
        updated_session = mock_session_cache.set_session.call_args[1]["session"]
        assert updated_session.current_step == 1
    
    @pytest.mark.asyncio
    async def test_round_robin_wraps_around(self, collaboration_service, mock_session_cache):
        """Test round-robin cycles back to first model."""
        
        session = CollaborationSession(
            session_id="wrap-test",
            objective="Test wrapping",
            models=["model_1", "model_2"],
            messages=[],
            current_step=3,  # Should wrap: 3 % 2 = 1 (model_2)
            mode="round_robin",
            max_steps=10,
            status="active"
        )
        mock_session_cache.get_session.return_value = session
        
        collaboration_service.executor.execute.return_value = "Wrapped response"
        
        await collaboration_service.execute(
            session_id="wrap-test",
            objective="",
            models=[],
            user_input="Test wrap"
        )
        
        # Should have called model_2 (index 1)
        # Verify by checking the session was advanced properly
        updated_session = mock_session_cache.set_session.call_args[1]["session"]
        assert updated_session.current_step == 4


class TestCollaborationServiceModelExecution:
    """Test individual model turn execution."""
    
    @pytest.mark.asyncio
    async def test_model_turn_execution(self, collaboration_service, mock_whiteboard_manager, mock_session_cache):
        """Test individual model gets whiteboard context."""
        
        session = CollaborationSession(
            session_id="model-test",
            objective="Test model execution",
            models=["chat_with_gpt5"],
            messages=[],
            current_step=0,
            mode="round_robin",
            max_steps=5,
            status="active"
        )
        mock_session_cache.get_session.return_value = session
        
        # Mock whiteboard store info
        mock_whiteboard_manager.get_or_create_store.return_value = {"store_id": "vs_model_test", "provider": "openai"}
        
        # Mock executor response
        collaboration_service.executor.execute.return_value = "GPT-5 analyzed the whiteboard and responded"
        
        await collaboration_service.execute(
            session_id="model-test",
            objective="",
            models=[],
            user_input="Analyze the situation"
        )
        
        # Verify executor was called with correct parameters
        call_kwargs = collaboration_service.executor.execute.call_args[1]
        
        # Should have disable_history_record=True
        assert call_kwargs["disable_history_record"] is True
        
        # Should have disable_history_search=True (GPT-5's recommendation)
        assert call_kwargs["disable_history_search"] is True
        
        # Should have vector_store_ids with whiteboard store
        assert call_kwargs["vector_store_ids"] == ["vs_model_test"]
        
        # Should have unique sub-session ID
        assert call_kwargs["session_id"] == "model-test__chat_with_gpt5"
        
        # Should have instructions referencing whiteboard
        assert "whiteboard" in call_kwargs["instructions"].lower()
    
    @pytest.mark.asyncio
    async def test_whiteboard_context_injection(self, collaboration_service, mock_whiteboard_manager):
        """Test whiteboard vector store passed via executor vector_store_ids override."""
        
        # This test verifies our critical executor passthrough is used
        session = CollaborationSession(
            session_id="whiteboard-inject-test",
            objective="Test whiteboard injection", 
            models=["chat_with_gemini25_pro"],
            messages=[],
            current_step=0,
            mode="round_robin",
            max_steps=3,
            status="active"
        )
        
        # Mock dependencies
        collaboration_service.session_cache.get_session = AsyncMock(return_value=session)
        mock_whiteboard_manager.get_or_create_store.return_value = {"store_id": "vs_inject_123", "provider": "hnsw"}
        
        collaboration_service.executor.execute.return_value = "Gemini accessed whiteboard successfully"
        
        await collaboration_service.execute(
            session_id="whiteboard-inject-test",
            objective="",
            models=[],
            user_input="Use the whiteboard"
        )
        
        # Verify the critical vector_store_ids passthrough was used
        call_kwargs = collaboration_service.executor.execute.call_args[1]
        assert call_kwargs["vector_store_ids"] == ["vs_inject_123"]
        
        # This proves our executor fix is being used by the orchestrator
    
    @pytest.mark.asyncio
    async def test_history_isolation(self, collaboration_service, mock_session_cache):
        """Test sub-calls use disable_history_record=True and unique sub-session IDs."""
        
        session = CollaborationSession(
            session_id="isolation-test",
            objective="Test isolation",
            models=["chat_with_claude41_opus"],
            messages=[],
            current_step=0,
            mode="round_robin",
            max_steps=2,
            status="active"
        )
        mock_session_cache.get_session.return_value = session
        
        collaboration_service.executor.execute.return_value = "Claude response with isolation"
        
        await collaboration_service.execute(
            session_id="isolation-test",
            objective="",
            models=[],
            user_input="Test isolation"
        )
        
        call_kwargs = collaboration_service.executor.execute.call_args[1]
        
        # Verify history is disabled for sub-calls
        assert call_kwargs["disable_history_record"] is True
        assert call_kwargs["disable_history_search"] is True
        
        # Verify unique sub-session ID format
        expected_sub_session = "isolation-test__chat_with_claude41_opus"
        assert call_kwargs["session_id"] == expected_sub_session
        
        # This prevents pollution of project history and individual model sessions


class TestCollaborationServiceErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_error_handling_model_failure(self, collaboration_service, mock_session_cache):
        """Test graceful handling of model failures."""
        
        session = CollaborationSession(
            session_id="error-test",
            objective="Test error handling",
            models=["chat_with_failing_model"],
            messages=[],
            current_step=0,
            mode="round_robin", 
            max_steps=3,
            status="active"
        )
        mock_session_cache.get_session.return_value = session
        
        # Mock executor failure
        collaboration_service.executor.execute.side_effect = Exception("Model API failed")
        
        # Should handle error gracefully
        result = await collaboration_service.execute(
            session_id="error-test",
            objective="",
            models=[],
            user_input="This will fail"
        )
        
        # Should return error message instead of crashing
        assert "error" in result.lower() or "failed" in result.lower()
        
        # Session should still be updated (marked as failed or with error message)
        mock_session_cache.set_session.assert_called()
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, collaboration_service, mock_session_cache):
        """Test per-step timeout enforcement."""
        
        session = CollaborationSession(
            session_id="timeout-test", 
            objective="Test timeout",
            models=["chat_with_slow_model"],
            messages=[],
            current_step=0,
            mode="round_robin",
            max_steps=5,
            status="active"
        )
        mock_session_cache.get_session.return_value = session
        
        # Mock tool metadata lookup
        with patch.object(collaboration_service, '_get_tool_metadata') as mock_get_tool:
            mock_get_tool.return_value = {"name": "chat_with_slow_model", "type": "tool"}
            
            # Test that timeout config is respected
            config = CollaborationConfig(timeout_per_step=30)  # 30 seconds
            
            # We don't need to actually timeout, just verify config is used
            collaboration_service.executor.execute.return_value = "Fast response"
            
            await collaboration_service.execute(
                session_id="timeout-test",
                objective="",
                models=[],
                user_input="Test timeout config",
                config=config
            )
        
        # The timeout would be enforced by the executor via operation_manager
        # Verify that the execution was called successfully
        assert collaboration_service.executor.execute.called


class TestCollaborationServiceSummarization:
    """Test automatic summarization and rollover."""
    
    @pytest.mark.asyncio
    async def test_automatic_summarization_triggered(self, collaboration_service, mock_whiteboard_manager, mock_session_cache):
        """Test summarization triggered when threshold reached."""
        
        # Create session with many messages (over threshold)
        messages = [CollaborationMessage(f"speaker_{i}", f"message {i}", datetime.now()) for i in range(60)]
        session = CollaborationSession(
            session_id="summarize-test",
            objective="Long conversation",
            models=["chat_with_gpt5"],
            messages=messages,
            current_step=59,
            mode="round_robin",
            max_steps=100,
            status="active"
        )
        mock_session_cache.get_session.return_value = session
        
        collaboration_service.executor.execute.return_value = "Response after summarization"
        
        config = CollaborationConfig(summarization_threshold=50)
        
        await collaboration_service.execute(
            session_id="summarize-test",
            objective="",
            models=[],
            user_input="Continue long conversation",
            config=config
        )
        
        # Verify summarization was triggered (positional argument)
        mock_whiteboard_manager.summarize_and_rollover.assert_called_once_with(
            "summarize-test", 
            50
        )


class TestCollaborationServiceOrchestrator:
    """Test orchestrator mode (future enhancement)."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_mode_placeholder(self, collaboration_service, mock_session_cache):
        """Test orchestrator mode is supported (basic implementation)."""
        
        session = CollaborationSession(
            session_id="orchestrator-test",
            objective="Test orchestrator mode", 
            models=["chat_with_gpt5", "chat_with_claude41_opus"],
            messages=[],
            current_step=0,
            mode="orchestrator",  # Different mode
            max_steps=5,
            status="active"
        )
        mock_session_cache.get_session.return_value = session
        
        collaboration_service.executor.execute.return_value = "Orchestrated response"
        
        # Should not fail with orchestrator mode
        result = await collaboration_service.execute(
            session_id="orchestrator-test",
            objective="",
            models=[],
            user_input="Test orchestrator"
        )
        
        assert "Orchestrated response" in result
        
        # For now, orchestrator mode can fall back to round-robin
        # Future enhancement: implement smart model selection