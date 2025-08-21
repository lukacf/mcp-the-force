"""Test executor vector_store_ids passthrough for Chatter collaboration."""

import os
import pytest
from unittest.mock import patch, AsyncMock
from mcp_the_force.tools.executor import ToolExecutor
from mcp_the_force.tools.registry import get_tool


@pytest.fixture(autouse=True)
def enable_mock_adapter():
    """Enable mock adapter for all tests in this module.""" 
    os.environ["MCP_ADAPTER_MOCK"] = "1"
    yield
    os.environ.pop("MCP_ADAPTER_MOCK", None)


@pytest.mark.asyncio
async def test_executor_passthrough_vector_store_ids():
    """Test executor accepts vector_store_ids for tools that don't declare it."""
    
    # Get a real tool that doesn't declare vector_store_ids parameter
    metadata = get_tool("search_project_history")
    assert metadata is not None, "search_project_history tool should be registered"
    
    executor = ToolExecutor()
    
    # Mock the service execution to capture the call
    with patch('mcp_the_force.local_services.search_history.HistorySearchService.execute') as mock_service:
        mock_service.return_value = {"results": "Mock search results"}
        
        # Test: Call executor with privileged vector_store_ids override
        test_vector_store_ids = ["vs_test_123", "vs_test_456"] 
        
        result = await executor.execute(
            metadata=metadata,
            query="test search",
            max_results="5",
            vector_store_ids=test_vector_store_ids  # This should be extracted but not interfere
        )
        
        # Verify the service was called (local service tool)
        assert mock_service.called
        
        # Verify we got a result
        assert "Mock search results" in result


@pytest.mark.asyncio  
async def test_executor_passthrough_without_vector_store_param():
    """Test that vector_store_ids can be passed even when tool doesn't expect it."""
    
    # Get search_project_history tool which doesn't have vector_store_ids parameter
    metadata = get_tool("search_project_history")
    executor = ToolExecutor()
    
    with patch('mcp_the_force.local_services.search_history.HistorySearchService.execute') as mock_service:
        mock_service.return_value = {"results": "Test results"}
        
        # This should not raise an error even though search_project_history
        # doesn't declare vector_store_ids as a parameter
        result = await executor.execute(
            metadata=metadata,
            query="test query", 
            vector_store_ids=["vs_should_not_break_anything"]
        )
        
        # Should execute successfully 
        assert mock_service.called
        assert "Test results" in result


@pytest.mark.asyncio
async def test_executor_logs_vector_store_override():
    """Test that executor logs the vector_store_ids override extraction."""
    
    metadata = get_tool("search_project_history")
    executor = ToolExecutor()
    
    with patch('mcp_the_force.local_services.search_history.HistorySearchService.execute') as mock_service, \
         patch('mcp_the_force.tools.executor.logger') as mock_logger:
        
        mock_service.return_value = {"results": "Mock results"}
        
        # Test with vector_store_ids override
        test_ids = ["vs_log_test"]
        
        await executor.execute(
            metadata=metadata,
            query="test",
            vector_store_ids=test_ids
        )
        
        # Verify debug logging was called for extraction
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if "vector_store_ids override" in str(call)]
        assert len(debug_calls) > 0, "Should log vector_store_ids override extraction"