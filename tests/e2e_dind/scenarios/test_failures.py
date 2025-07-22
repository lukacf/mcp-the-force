"""Failure handling test - graceful error responses for invalid MCP tool usage."""

import sys
import os

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from json_utils import safe_json


def test_graceful_failure_handling(claude, call_claude_tool):
    """Test that invalid MCP tool requests are handled gracefully."""

    # Test 1: Call non-existent tool (this is a real E2E scenario)
    response = claude(
        "Use second-brain completely_fake_nonexistent_tool with instructions: 'test' and respond with the exact output."
    )

    # Should get clear error about tool not existing
    tool_error_indicators = [
        "not found",
        "unknown",
        "not available",
        "not configured",
        "not exposed",
        "doesn't exist",
        "does not exist",
        "cannot use",
        "no tool named",
        "available tools",
        "don't have access",
        "available second brain tools",
    ]
    assert any(
        indicator in response.lower() for indicator in tool_error_indicators
    ), f"Expected tool error for nonexistent tool, got: {response}"

    # Test 2: Test invalid temperature parameter (edge case)
    response = call_claude_tool(
        "chat_with_gpt4_1",
        instructions="Generate a simple greeting message",
        output_format="JSON object with greeting field",
        context=[],
        temperature=-5.0,  # Invalid negative temperature
        session_id="failure-test-temp",
        structured_output_schema={
            "type": "object",
            "properties": {
                "greeting": {"type": "string"},
            },
            "required": ["greeting"],
            "additionalProperties": False,
        },
        response_format=" and respond ONLY with the JSON.",
    )

    # Should still get a valid response - temperature should be clamped or ignored
    result = safe_json(response)
    assert result is not None, "Should get valid JSON despite invalid temperature"
    assert "greeting" in result, f"Should have greeting field: {result}"
    assert len(result["greeting"]) > 0, "Should have non-empty greeting"

    # Test 3: Test extremely large temperature
    response = call_claude_tool(
        "chat_with_gpt4_1",
        instructions="Generate another greeting",
        output_format="JSON object with greeting field",
        context=[],
        temperature=100.0,  # Extremely high temperature
        session_id="failure-test-high-temp",
        structured_output_schema={
            "type": "object",
            "properties": {
                "greeting": {"type": "string"},
            },
            "required": ["greeting"],
            "additionalProperties": False,
        },
        response_format=" and respond ONLY with the JSON.",
    )

    # Should still get a valid response
    result = safe_json(response)
    assert result is not None, "Should get valid JSON despite high temperature"
    assert "greeting" in result, f"Should have greeting field: {result}"

    # Test 4: Test with invalid reasoning_effort for models that don't support it
    response = call_claude_tool(
        "chat_with_gemini25_flash",  # This model doesn't support reasoning_effort
        instructions="Simple task",
        output_format="JSON with status",
        context=[],
        session_id="failure-test-reasoning",
        reasoning_effort="high",  # Invalid parameter for this model
        structured_output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
            },
            "required": ["status"],
        },
        response_format=" and respond ONLY with the JSON.",
    )

    # Should handle gracefully - either ignore the parameter or return an error
    # But should not crash
    assert response is not None
    assert len(response) > 0

    print("✅ All failure handling tests passed!")
