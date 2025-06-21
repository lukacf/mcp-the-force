"""Debug test for session handling."""
import pytest
import json

pytestmark = pytest.mark.e2e


class TestSessionDebug:
    """Debug tests for session functionality."""
    
    @pytest.mark.timeout(120)
    def test_simple_session_gpt4(self, claude_code):
        """Simple test to debug GPT-4.1 session handling."""
        # Fixed session ID
        session_id = "debug-session-123"
        
        # First message
        # Try different parameter formats
        # Method 1: Direct parameter specification
        output1 = claude_code(
            f'Use second-brain chat_with_gpt4_1 with instructions="Remember this: The secret word is BANANA. Just say OK.", '
            f'output_format="text", context=[], and session_id="{session_id}"'
        )
        print("\n=== TURN 1 ===")
        print(f"Session ID: {session_id}")
        print(f"Output: {output1.strip()}")
        
        # Second message - should remember
        output2 = claude_code(
            f'Use second-brain chat_with_gpt4_1 with instructions="What is the secret word? Just say the word.", '
            f'output_format="text", context=[], and session_id="{session_id}"'
        )
        print("\n=== TURN 2 ===")
        print(f"Session ID: {session_id}")
        print(f"Output: {output2.strip()}")
        
        # Check if it remembered
        assert "banana" in output2.lower(), f"Expected BANANA but got: {output2}"
    
    @pytest.mark.timeout(600)  # 10 minutes for o3
    def test_simple_session_o3(self, claude_code):
        """Test o3 session handling."""
        # Fixed session ID
        session_id = "debug-o3-session-456"
        
        # First message
        args1 = {
            "instructions": "Remember this number: 42. Just acknowledge.",
            "output_format": "text",
            "context": [],
            "session_id": session_id,
            "reasoning_effort": "low"  # Keep it fast for testing
        }
        output1 = claude_code(
            f'Use second-brain chat_with_o3 with {json.dumps(args1)}'
        )
        print("\n=== O3 TURN 1 ===")
        print(f"Output: {output1.strip()}")
        
        # Second message - should remember
        args2 = {
            "instructions": "What number did I ask you to remember? Just say the number.",
            "output_format": "text",
            "context": [],
            "session_id": session_id,
            "reasoning_effort": "low"
        }
        output2 = claude_code(
            f'Use second-brain chat_with_o3 with {json.dumps(args2)}'
        )
        print("\n=== O3 TURN 2 ===")
        print(f"Output: {output2.strip()}")
        
        # Check if it remembered
        assert "42" in output2, f"Expected 42 but got: {output2}"