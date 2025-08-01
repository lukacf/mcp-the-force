"""Test the disable_history_search parameter fix."""

import sys
import os

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from json_utils import safe_json


def test_disable_history_search_fix(call_claude_tool):
    """Test that disable_history_search parameter works correctly with JSON encoding."""

    # Define a simple schema
    test_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "success": {"type": "boolean"},
        },
        "required": ["message", "success"],
        "additionalProperties": False,
    }

    # Test with disable_history_search set to true (as string)
    response = call_claude_tool(
        "chat_with_gpt41",
        instructions="Say 'test passed' and confirm success",
        output_format="JSON with message and success fields",
        context=[],
        session_id="test-disable-memory",
        disable_history_search="true",  # This should now be properly quoted
        disable_history_record="true",  # Also disable history recording
        structured_output_schema=test_schema,
        response_format="respond ONLY with the JSON",
    )

    # Validate response
    result = safe_json(response)
    assert result is not None, f"Failed to parse JSON: {response}"
    assert result["success"] is True, f"Test not successful: {result}"
    assert "test passed" in result["message"].lower(), f"Wrong message: {result}"

    print("✅ disable_history_search parameter test passed!")
