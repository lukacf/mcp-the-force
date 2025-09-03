"""Simplified tests for group_think to debug async mocking issues."""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch

from mcp_the_force.local_services.collaboration_service import CollaborationService
from mcp_the_force.types.collaboration import CollaborationConfig


class TestGroupThinkSimple:
    """Simplified tests to debug async issues."""

    @pytest.mark.asyncio
    async def test_collaboration_service_basic_mock(self):
        """Test basic mocking of collaboration service."""
        
        # Create service with properly mocked dependencies
        mock_executor = AsyncMock()
        mock_whiteboard = AsyncMock()
        mock_session_cache = AsyncMock()
        
        # Set up return values
        mock_whiteboard.get_or_create_store.return_value = {
            "store_id": "vs_test",
            "provider": "openai"
        }
        mock_session_cache.get_metadata.return_value = None
        mock_executor.execute.return_value = "Mock model response"
        
        service = CollaborationService(
            executor=mock_executor,
            whiteboard_manager=mock_whiteboard, 
            session_cache=mock_session_cache,
        )
        
        # Mock the progress installer to avoid installation complexity
        with patch.object(service, '_ensure_progress_components_installed', new_callable=AsyncMock) as mock_installer:
            mock_installer.return_value = None
            
            # Mock get_settings to avoid config complexity
            with patch('mcp_the_force.config.get_settings') as mock_settings:
                mock_settings.return_value.logging.project_path = "/test/project"
                
                try:
                    result = await service.execute(
                        session_id="simple-test",
                        objective="Simple test objective",
                        models=["chat_with_gpt5_mini"],
                        output_format="Simple test result",
                        discussion_turns=1,
                        validation_rounds=0,  # Skip validation for simplicity
                    )
                    
                    # If we get here, the basic async mocking works
                    assert result is not None
                    print(f"Success! Result: {result[:100]}...")
                    
                except Exception as e:
                    print(f"Error: {e}")
                    # Print the full traceback for debugging
                    import traceback
                    traceback.print_exc()
                    raise

    @pytest.mark.asyncio 
    async def test_individual_phases_mocked(self):
        """Test individual phase methods with proper mocking."""
        
        mock_executor = AsyncMock()
        mock_whiteboard = AsyncMock()
        mock_session_cache = AsyncMock()
        
        service = CollaborationService(
            executor=mock_executor,
            whiteboard_manager=mock_whiteboard,
            session_cache=mock_session_cache,
        )
        
        # Test contract building (this should be simple and not require complex mocking)
        contract = await service._build_deliverable_contract(
            objective="Test objective",
            output_format="JSON response",
            user_input="Test input",
            session_id="test-session"
        )
        
        assert contract.objective == "Test objective"
        assert contract.output_format == "JSON response"
        print("✓ Contract building works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])