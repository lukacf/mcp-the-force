"""Cross-tool scenario tests."""
import pytest
import json
import tempfile
from pathlib import Path

pytestmark = pytest.mark.e2e


class TestE2EScenarios:
    """More complex scenarios testing tool interactions."""
    
    def test_vector_store_workflow(self, claude_code):
        """Test creating and using a vector store."""
        # Use specific Python files from the project
        files = [
            "/app/mcp_second_brain/server.py",
            "/app/mcp_second_brain/tools/definitions.py",
            "/app/README.md"
        ]
        files_json = json.dumps(files)
        
        # Create vector store
        output = claude_code(
            f'Use second-brain create_vector_store_tool with files {files_json}'
        )
        
        # Should create successfully
        assert "vector_store_id" in output
        assert not "error" in output.lower()
    
    def test_model_comparison(self, claude_code):
        """Test comparing outputs from different models."""
        prompt = "What is 2+2? Answer with just the number."
        
        # Try with fast model
        flash_output = claude_code(
            f'Use second-brain chat_with_gemini25_flash with instructions "{prompt}", '
            'output_format "text", and context []'
        )
        
        # Should contain "4"
        assert "4" in flash_output
    
    @pytest.mark.skip(reason="o3 is expensive - enable manually for release testing")
    def test_o3_session(self, claude_code):
        """Test o3 with session continuity."""
        # First query
        output1 = claude_code(
            'Use second-brain chat_with_o3 with instructions "Remember the number 42", '
            'output_format "text", context [], and session_id "test-session-1"'
        )
        
        # Follow-up query
        output2 = claude_code(
            'Use second-brain chat_with_o3 with instructions "What number did I ask you to remember?", '
            'output_format "text", context [], and session_id "test-session-1"'
        )
        
        # Should remember
        assert "42" in output2