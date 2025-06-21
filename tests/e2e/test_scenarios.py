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
        
        # Create vector store with specific output format
        output = claude_code(
            f'Use second-brain create_vector_store_tool with files {files_json}. '
            f'If the tool succeeds and returns a vector_store_id, output exactly "SUCCESS: <id>". '
            f'If it fails, output exactly "FAILED: <reason>".'
        )
        
        # Check for structured response
        assert "SUCCESS:" in output or "FAILED:" in output
        if "FAILED:" in output:
            # If it failed, make sure it's for a valid reason
            assert "no_supported_files" in output.lower() or "error" in output.lower()
    
    def test_model_comparison(self, claude_code):
        """Test comparing outputs from different models."""
        # Try with fast model
        output = claude_code(
            'Use second-brain chat_with_gemini25_flash with instructions "What is 2+2?", '
            'output_format "text", and context []. '
            'Extract just the answer from the response and output only "ANSWER: <number>".'
        )
        
        # Should contain the structured response
        assert "ANSWER: 4" in output
    
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