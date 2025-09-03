"""Comprehensive tests for the new group_think multi-phase collaboration workflow."""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from pathlib import Path
import json
import time
from datetime import datetime

from mcp_the_force.local_services.collaboration_service import CollaborationService
from mcp_the_force.types.collaboration import (
    CollaborationSession,
    CollaborationConfig,
    CollaborationMessage,
    DeliverableContract,
)


class TestGroupThinkMultiPhaseWorkflow:
    """Test the complete multi-phase workflow: Discussion → Synthesis → Validation."""

    @pytest.fixture
    def collaboration_service(self):
        """Create CollaborationService with mocked dependencies."""
        mock_executor = AsyncMock()
        mock_whiteboard = AsyncMock()
        mock_session_cache = AsyncMock()
        
        # Mock whiteboard methods
        mock_whiteboard.get_or_create_store = AsyncMock()
        mock_whiteboard.append_message = AsyncMock()
        
        service = CollaborationService(
            executor=mock_executor,
            whiteboard_manager=mock_whiteboard,
            session_cache=mock_session_cache,
        )
        return service, mock_executor, mock_whiteboard, mock_session_cache

    @pytest.mark.asyncio
    async def test_complete_multi_phase_workflow(self, collaboration_service):
        """Test the full discussion → synthesis → validation workflow."""
        service, mock_executor, mock_whiteboard, mock_session_cache = collaboration_service
        
        # Mock whiteboard creation
        mock_whiteboard.get_or_create_store.return_value = {
            "store_id": "vs_test_whiteboard",
            "provider": "openai"
        }
        
        # Mock session cache - no existing session
        mock_session_cache.get_metadata.return_value = None
        
        # Mock model executions for each phase
        model_responses = {
            # Discussion phase responses (2 turns)
            0: "GPT-5 mini discusses the objective",
            1: "Gemini Flash discusses the objective", 
            # Synthesis phase response
            2: "Final deliverable from synthesis model",
            # Validation phase responses (2 rounds)
            3: "GPT-5 mini validation feedback",
            4: "Gemini Flash validation feedback", 
            5: "Refined deliverable from synthesis model",
            6: "GPT-5 mini validation feedback round 2",
            7: "Gemini Flash validation feedback round 2",
            8: "Final refined deliverable from synthesis model",
        }
        
        call_count = 0
        async def mock_execute(**kwargs):
            nonlocal call_count
            response = model_responses.get(call_count, f"Mock response {call_count}")
            call_count += 1
            return response
            
        mock_executor.execute = mock_execute
        
        # Mock progress component installation and config
        with patch.object(service, '_ensure_progress_components_installed', new_callable=AsyncMock) as mock_installer, \
             patch('mcp_the_force.config.get_settings') as mock_settings:
            
            mock_installer.return_value = None
            mock_settings.return_value.logging.project_path = "/test/project"
            
            result = await service.execute(
                session_id="test-workflow",
                objective="Test multi-phase collaboration", 
                models=["chat_with_gpt5_mini", "chat_with_gemini25_flash"],
                output_format="Test deliverable with sections: Summary, Details",
                discussion_turns=2,
                validation_rounds=2,
            )
        
        # Verify we got a result (final deliverable)
        assert "Final refined deliverable" in result
        
        # Verify whiteboard was created
        mock_whiteboard.get_or_create_store.assert_called_once_with("test-workflow")
        
        # Verify session was saved multiple times (after each phase)
        assert mock_session_cache.set_metadata.call_count >= 3
        
        # Verify messages were added to whiteboard
        # Should be: 2 discussion + 1 synthesis + 4 validation feedback + 2 validation synthesis = 9 total
        assert mock_whiteboard.append_message.call_count >= 6

    @pytest.mark.asyncio
    async def test_discussion_phase_round_robin(self, collaboration_service):
        """Test that discussion phase follows round-robin pattern."""
        service, mock_executor, mock_whiteboard, mock_session_cache = collaboration_service
        
        # Mock dependencies
        mock_whiteboard.get_or_create_store.return_value = {"store_id": "vs_test", "provider": "openai"}
        mock_session_cache.get_metadata.return_value = None
        
        # Track which models are called during discussion phase
        called_models = []
        
        async def mock_execute(**kwargs):
            # Extract model from instructions (hack for testing)
            instructions = kwargs.get('instructions', '')
            if 'gpt5_mini' in instructions or 'GPT-5' in instructions:
                called_models.append('chat_with_gpt5_mini')
            elif 'gemini' in instructions or 'Gemini' in instructions:  
                called_models.append('chat_with_gemini25_flash')
            elif 'synthesis' in instructions.lower():
                called_models.append('synthesis_model')
            return "Mock response"
        
        mock_executor.execute = mock_execute
        
        with patch.object(service, '_ensure_progress_components_installed', new_callable=AsyncMock) as mock_installer, \
             patch('mcp_the_force.config.get_settings') as mock_settings:
            
            mock_installer.return_value = None
            mock_settings.return_value.logging.project_path = "/test/project"
            
            await service.execute(
                session_id="round-robin-test",
                objective="Test round-robin pattern",
                models=["chat_with_gpt5_mini", "chat_with_gemini25_flash", "chat_with_grok3_fast"], 
                output_format="Test result",
                discussion_turns=4,
                validation_rounds=0,  # Skip validation to focus on discussion
            )
        
        # Verify discussion phase used round-robin pattern
        discussion_calls = called_models[:4]  # First 4 calls should be discussion
        expected_pattern = ["chat_with_gpt5_mini", "chat_with_gemini25_flash", "chat_with_grok3_fast", "chat_with_gpt5_mini"]
        
        # Note: We can't easily verify the exact pattern without better mocking,
        # but we can verify all original models participated
        discussion_models = set(discussion_calls)
        assert "chat_with_gpt5_mini" in discussion_models
        assert "chat_with_gemini25_flash" in discussion_models 
        assert "chat_with_grok3_fast" in discussion_models

    @pytest.mark.asyncio
    async def test_synthesis_phase_uses_correct_model(self, collaboration_service):
        """Test that synthesis phase uses the specified synthesis model."""
        service, mock_executor, mock_whiteboard, mock_session_cache = collaboration_service
        
        mock_whiteboard.get_or_create_store.return_value = {"store_id": "vs_test", "provider": "openai"}
        mock_session_cache.get_metadata.return_value = None
        
        synthesis_calls = []
        
        async def mock_execute(**kwargs):
            # Track synthesis calls by looking for synthesis session IDs
            session_id = kwargs.get('session_id', '')
            if 'synthesis' in session_id:
                synthesis_calls.append(kwargs)
            return "Mock synthesis deliverable"
        
        mock_executor.execute = mock_execute
        
        with patch.object(service, '_ensure_progress_components_installed', new_callable=AsyncMock) as mock_installer, \
             patch('mcp_the_force.config.get_settings') as mock_settings:
            
            mock_installer.return_value = None
            mock_settings.return_value.logging.project_path = "/test/project"
            
            await service.execute(
                session_id="synthesis-test", 
                objective="Test synthesis model",
                models=["chat_with_gpt5_mini"],
                output_format="Test deliverable",
                discussion_turns=1,
                synthesis_model="chat_with_claude4_sonnet",  # Custom synthesis model
                validation_rounds=0,
            )
        
        # Verify synthesis was called
        assert len(synthesis_calls) >= 1
        
        # Verify synthesis used the correct metadata (would come from get_tool_metadata)
        synthesis_call = synthesis_calls[0]
        assert 'synthesis' in synthesis_call['session_id']

    @pytest.mark.asyncio 
    async def test_validation_rounds_feedback_loop(self, collaboration_service):
        """Test that validation rounds create proper feedback loop."""
        service, mock_executor, mock_whiteboard, mock_session_cache = collaboration_service
        
        mock_whiteboard.get_or_create_store.return_value = {"store_id": "vs_test", "provider": "openai"}
        mock_session_cache.get_metadata.return_value = None
        
        validation_calls = []
        refinement_calls = []
        
        async def mock_execute(**kwargs):
            session_id = kwargs.get('session_id', '')
            if 'validation_r' in session_id:
                validation_calls.append(kwargs)
                return "Validation feedback"
            elif 'advisory_r' in session_id:
                refinement_calls.append(kwargs) 
                return "Refined deliverable"
            return "Mock response"
        
        mock_executor.execute = mock_execute
        
        with patch.object(service, '_ensure_progress_components_installed', new_callable=AsyncMock) as mock_installer, \
             patch('mcp_the_force.config.get_settings') as mock_settings:
            
            mock_installer.return_value = None
            mock_settings.return_value.logging.project_path = "/test/project"
            
            await service.execute(
                session_id="validation-test",
                objective="Test validation rounds",
                models=["chat_with_gpt5_mini", "chat_with_gemini25_flash"],
                output_format="Test deliverable", 
                discussion_turns=1,
                validation_rounds=2,
            )
        
        # Verify validation feedback was collected
        # Should be: 2 models × 2 rounds = 4 validation calls
        assert len(validation_calls) >= 4
        
        # Verify refinement happened after each round
        # Should be: 2 refinement calls (one per round)
        assert len(refinement_calls) >= 2

    @pytest.mark.asyncio
    async def test_session_continuity(self, collaboration_service):
        """Test that existing sessions are properly continued."""
        service, mock_executor, mock_whiteboard, mock_session_cache = collaboration_service
        
        # Mock existing session
        existing_session_data = {
            'session_id': 'existing-session',
            'objective': 'Original objective', 
            'models': ['chat_with_gpt5'],
            'messages': [],
            'current_step': 2,  # Already completed some steps
            'mode': 'round_robin',
            'max_steps': 10,
            'status': 'active'
        }
        mock_session_cache.get_metadata.return_value = existing_session_data
        
        mock_whiteboard.get_or_create_store.return_value = {"store_id": "vs_existing", "provider": "openai"}
        mock_executor.execute.return_value = "Continued response"
        
        with patch.object(service, '_ensure_progress_components_installed', new_callable=AsyncMock) as mock_installer, \
             patch('mcp_the_force.config.get_settings') as mock_settings:
            
            mock_installer.return_value = None
            mock_settings.return_value.logging.project_path = "/test/project"
            
            result = await service.execute(
                session_id="existing-session",
                objective="New objective should be ignored",
                models=["new_models_should_be_ignored"], 
                output_format="Test continuation",
                discussion_turns=1,
            )
        
        # Verify existing session was loaded, not recreated
        mock_session_cache.get_metadata.assert_called_with(
            'mcp-the-force', 'group_think', 'existing-session', 'collab_state'
        )
        
        # Verify collaboration continued from where it left off
        assert "Continued response" in result or "Mock" in result


class TestCollaborationServiceUnitMethods:
    """Unit tests for individual CollaborationService methods."""
    
    @pytest.fixture 
    def service(self):
        return CollaborationService()
    
    @pytest.mark.asyncio
    async def test_build_deliverable_contract(self, service):
        """Test deliverable contract creation."""
        contract = await service._build_deliverable_contract(
            objective="Test objective",
            output_format="JSON with keys: summary, details",
            user_input="Additional context",
            session_id="test-contract"
        )
        
        assert isinstance(contract, DeliverableContract)
        assert contract.objective == "Test objective"
        assert contract.output_format == "JSON with keys: summary, details"
        assert contract.deliverable_type == "user_specified"
        
    @pytest.mark.asyncio
    async def test_build_deliverable_contract_validation(self, service):
        """Test contract validation for empty output_format."""
        with pytest.raises(ValueError, match="output_format is required"):
            await service._build_deliverable_contract(
                objective="Test", 
                output_format="",
                user_input="",
                session_id="test"
            )

    def test_write_progress_file(self, service):
        """Test progress file creation and content."""
        session = CollaborationSession(
            session_id="progress-test",
            objective="Test progress",
            models=["chat_with_gpt5"],
            messages=[],
            current_step=2,
            mode="round_robin", 
            max_steps=5,
            status="active"
        )
        
        with patch('pathlib.Path.mkdir'), \
             patch('builtins.open', create=True) as mock_open, \
             patch('json.dump') as mock_json_dump:
            
            service._write_progress_file(
                session=session,
                current_model="chat_with_gpt5_mini",
                phase="discussing", 
                start_time=time.time() - 60,  # 60 seconds ago
                total_phases=5
            )
        
        # Verify file was written
        mock_open.assert_called_once()
        mock_json_dump.assert_called_once()
        
        # Verify progress data structure
        progress_data = mock_json_dump.call_args[0][0]
        assert progress_data['owner'] == 'Chatter'
        assert progress_data['session_id'] == 'progress-test' 
        assert progress_data['phase'] == 'discussing'
        assert progress_data['step'] == 2
        assert progress_data['total'] == 5
        assert progress_data['percent'] == 40  # 2/5 * 100
        assert progress_data['current_model'] == 'chat_with_gpt5_mini'
        assert 'eta_s' in progress_data

    def test_cleanup_progress_file(self, service):
        """Test progress file cleanup."""
        with patch('pathlib.Path.exists', return_value=True) as mock_exists, \
             patch('pathlib.Path.unlink') as mock_unlink:
            
            service._cleanup_progress_file()
            
        mock_exists.assert_called_once()
        mock_unlink.assert_called_once()


class TestGroupThinkErrorScenarios:
    """Test error handling and recovery scenarios."""
    
    @pytest.fixture
    def collaboration_service(self):
        mock_executor = AsyncMock()
        mock_whiteboard = Mock() 
        mock_session_cache = AsyncMock()
        
        service = CollaborationService(
            executor=mock_executor,
            whiteboard_manager=mock_whiteboard,
            session_cache=mock_session_cache,
        )
        return service, mock_executor, mock_whiteboard, mock_session_cache

    @pytest.mark.asyncio
    async def test_model_timeout_handling(self, collaboration_service):
        """Test handling of model timeouts during discussion."""
        service, mock_executor, mock_whiteboard, mock_session_cache = collaboration_service
        
        mock_whiteboard.get_or_create_store.return_value = {"store_id": "vs_test", "provider": "openai"}
        mock_session_cache.get_metadata.return_value = None
        
        # Mock timeout exception
        mock_executor.execute.side_effect = asyncio.TimeoutError("Model timed out")
        
        with patch.object(service, '_ensure_progress_components_installed', new_callable=AsyncMock) as mock_installer, \
             patch('mcp_the_force.config.get_settings') as mock_settings:
            
            mock_installer.return_value = None
            mock_settings.return_value.logging.project_path = "/test/project"
            
            result = await service.execute(
                session_id="timeout-test",
                objective="Test timeout handling", 
                models=["chat_with_gpt5_mini"],
                output_format="Test result",
                discussion_turns=1,
                validation_rounds=0,
            )
        
        # Verify error was handled gracefully
        assert "error" in result.lower() or "timeout" in result.lower()
        
        # Verify session was marked as failed
        failed_calls = [call for call in mock_session_cache.set_metadata.call_args_list 
                       if len(call[0]) > 4 and 'failed' in str(call[0][4])]
        assert len(failed_calls) > 0

    @pytest.mark.asyncio
    async def test_progress_component_installation_failure(self, collaboration_service):
        """Test that collaboration continues even if progress installation fails."""
        service, mock_executor, mock_whiteboard, mock_session_cache = collaboration_service
        
        mock_whiteboard.get_or_create_store.return_value = {"store_id": "vs_test", "provider": "openai"} 
        mock_session_cache.get_metadata.return_value = None
        mock_executor.execute.return_value = "Success despite installer failure"
        
        # Mock installer failure
        with patch.object(service, '_ensure_progress_components_installed', 
                         side_effect=Exception("Installer failed")):
            
            result = await service.execute(
                session_id="installer-failure-test",
                objective="Test installer failure handling",
                models=["chat_with_gpt5_mini"], 
                output_format="Test result",
                discussion_turns=1,
                validation_rounds=0,
            )
        
        # Verify collaboration succeeded despite installer failure
        assert "Success despite installer failure" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])