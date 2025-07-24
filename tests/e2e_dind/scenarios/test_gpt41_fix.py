"""Test GPT-4.1 multi-turn conversation without disable_memory_search."""

import sys
import os

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from json_utils import safe_json


def test_gpt41_multi_turn_fixed(call_claude_tool):
    """Test simple two-turn conversation with GPT-4.1 - fixed version."""

    session_id = "simple-gpt41-session-fixed"

    # Define simple schemas without pattern constraints
    storage_schema = {
        "type": "object",
        "properties": {
            "stored_value": {"type": "string"},
            "confirmed": {"type": "boolean"},
        },
        "required": ["stored_value", "confirmed"],
        "additionalProperties": False,
    }

    recall_schema = {
        "type": "object",
        "properties": {
            "recalled_value": {"type": "string"},
            "found": {"type": "boolean"},
        },
        "required": ["recalled_value", "found"],
        "additionalProperties": False,
    }

    # Turn 1: Store a simple value using GPT-4.1 (WITHOUT disable_memory_search)
    response = call_claude_tool(
        "chat_with_gpt4_1",
        instructions="Remember this code: ABC-123-XYZ",
        output_format="JSON confirming what was stored",
        context=[],
        session_id=session_id,
        # disable_memory_search="true",  # REMOVED - this might be causing issues
        structured_output_schema=storage_schema,
        response_format="respond ONLY with the JSON",
    )

    # Validate storage
    result = safe_json(response)
    assert result is not None, f"Failed to parse JSON: {response}"
    assert result["confirmed"] is True, f"Storage not confirmed: {result}"
    assert "ABC-123-XYZ" in result["stored_value"], f"Code not stored: {result}"

    # Turn 2: Recall the value in the same session
    response = call_claude_tool(
        "chat_with_gpt4_1",
        instructions="What was the code I asked you to remember?",
        output_format="JSON with the recalled code",
        context=[],
        session_id=session_id,
        # disable_memory_search="true",  # REMOVED
        structured_output_schema=recall_schema,
        response_format="respond ONLY with the JSON",
    )

    # Validate recall
    result = safe_json(response)
    assert result is not None, f"Failed to parse recall JSON: {response}"
    assert result["found"] is True, f"Code not found in session: {result}"
    assert "ABC-123-XYZ" in result["recalled_value"], f"Wrong code recalled: {result}"

    print("✅ GPT-4.1 multi-turn conversation test passed!")
