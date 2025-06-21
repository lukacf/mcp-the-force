"""Test that tools are actually registered when server starts."""
import pytest
import importlib
import sys


class TestToolRegistration:
    """Test tool registration flow."""
    
    def test_tools_are_registered_on_import(self):
        """Test that importing the server registers all tools."""
        # Just import and check - don't try to manipulate module state
        # as other tests may have already imported these modules
        from mcp_second_brain import server
        from mcp_second_brain.tools.registry import list_tools
        
        # Check tools are registered
        tools = list_tools()
        
        # We expect at least 5 model tools
        expected_tools = [
            'chat_with_gemini25_pro',
            'chat_with_gemini25_flash', 
            'chat_with_o3',
            'chat_with_o3_pro',
            'chat_with_gpt4_1'
        ]
        
        for tool_name in expected_tools:
            assert tool_name in tools, f"Tool {tool_name} not registered"
            
        # Verify each tool has proper metadata
        for tool_id, metadata in tools.items():
            if tool_id == metadata.id:  # Skip aliases
                assert metadata.model_config['model_name'], f"Tool {tool_id} missing model_name"
                assert metadata.model_config['adapter_class'], f"Tool {tool_id} missing adapter_class"
                assert metadata.model_config['description'], f"Tool {tool_id} missing description"
                assert len(metadata.parameters) > 0, f"Tool {tool_id} has no parameters"
    
    def test_no_duplicate_registrations(self):
        """Test that multiple imports don't duplicate tool registrations."""
        from mcp_second_brain import server
        from mcp_second_brain.tools.registry import list_tools
        
        # Get initial count
        tools_before = list_tools()
        primary_tools_before = [t for t, m in tools_before.items() if t == m.id]
        
        # Force reimport
        importlib.reload(sys.modules['mcp_second_brain.server'])
        
        # Check count hasn't changed
        tools_after = list_tools()  
        primary_tools_after = [t for t, m in tools_after.items() if t == m.id]
        
        assert len(primary_tools_before) == len(primary_tools_after), \
            "Tool count changed after reimport"