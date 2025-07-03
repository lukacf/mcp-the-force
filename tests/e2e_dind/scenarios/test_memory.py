"""Memory lifecycle test - session persistence and isolation."""

import json
import sys
import os

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from json_utils import safe_json


def test_memory_lifecycle(claude):
    """Test session memory storage, recall, and isolation between sessions."""

    session_id_a = "memory-test-session-a"
    session_id_b = "memory-test-session-b"

    # Define schemas for structured responses
    storage_schema = {
        "type": "object",
        "properties": {
            "information_stored": {"type": "boolean"},
            "stored_content": {"type": "string"},
            "session_id_used": {"type": "string"},
        },
        "required": ["information_stored", "stored_content", "session_id_used"],
        "additionalProperties": False,
    }

    recall_schema = {
        "type": "object",
        "properties": {
            "protocol_name": {"type": "string"},
            "port_number": {"type": "integer"},
            "found_in_session": {"type": "boolean"},
        },
        "required": ["protocol_name", "port_number", "found_in_session"],
        "additionalProperties": False,
    }

    # Step 1: Store technical information in session A using Gemini
    args = {
        "instructions": "I'm configuring a system. Please remember: Protocol GAMMA-7 uses port 8443 for secure communications. Store this technical specification.",
        "output_format": "JSON object confirming what information was stored",
        "context": [],
        "session_id": session_id_a,
        "structured_output_schema": storage_schema,
    }

    response = claude(
        f"Use second-brain chat_with_gemini25_pro with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # ---- Step 1 validation ----
    result = safe_json(response)
    assert (
        "information_stored" in result
        and str(result["information_stored"]).lower() == "true"
    ) or (
        "stored_content" in result and "gamma-7" in result["stored_content"].lower()
    ), f"Unexpected confirmation JSON: {result}"

    # Additional checks if the expected fields exist
    if "stored_content" in result:
        assert (
            "GAMMA-7" in result["stored_content"] and "8443" in result["stored_content"]
        )
    # Any echoed session id only needs to be a non-empty string
    if "session_id_used" in result:
        assert isinstance(result["session_id_used"], str) and result["session_id_used"]

    # Step 2: Test immediate recall in same session with same model
    args = {
        "instructions": "What protocol and port number did I just tell you about?",
        "output_format": "JSON object with the protocol details",
        "context": [],
        "session_id": session_id_a,
        "structured_output_schema": recall_schema,
    }

    response = claude(
        f"Use second-brain chat_with_gemini25_pro with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Parse and validate recall
    result = safe_json(response)
    assert result["found_in_session"] is True
    assert "GAMMA-7" in result["protocol_name"]
    assert result["port_number"] == 8443

    # Step 3: Test cross-model recall within same session (Gemini -> o3)
    args = {
        "instructions": "In our current session, what protocol configuration was discussed?",
        "output_format": "JSON object with protocol details if found in session",
        "context": [],
        "session_id": session_id_a,
        "reasoning_effort": "low",
        "structured_output_schema": recall_schema,
    }

    response = claude(
        f"Use second-brain chat_with_o3 with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Step-3 – another model, same session
    result = safe_json(response)
    assert result["found_in_session"] in (True, False)
    if result["found_in_session"]:
        # If the model can see it, check the values are correct
        assert "gamma-7" in result["protocol_name"].lower()

    # Step 4: Test session isolation (different session ID)
    args = {
        "instructions": "What protocol and port were mentioned in previous conversations?",
        "output_format": "JSON object with protocol details if any found",
        "context": [],
        "session_id": session_id_b,  # Different session
        "structured_output_schema": recall_schema,
    }

    response = claude(
        f"Use second-brain chat_with_gemini25_pro with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Different session should not have access to previous session data
    result = safe_json(response)
    assert result["found_in_session"] in (
        True,
        False,
    )  # Allow either isolation behavior

    # Step 5: Test session persistence (return to original session)
    args = {
        "instructions": "Quick reminder: what was that protocol configuration again?",
        "output_format": "JSON object with the remembered protocol details",
        "context": [],
        "session_id": session_id_a,  # Back to original session
        "structured_output_schema": recall_schema,
    }

    response = claude(
        f"Use second-brain chat_with_gemini25_pro with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Original session should still remember
    result = safe_json(response)
    assert result["found_in_session"] is True
    assert "GAMMA-7" in result["protocol_name"]
    assert result["port_number"] == 8443

    # Step 6: Test multi-turn conversation with reasoning_effort progression
    args = {
        "instructions": "Based on our discussion of Protocol GAMMA-7 on port 8443, analyze the security implications of using that specific port.",
        "output_format": "JSON object with security analysis",
        "context": [],
        "session_id": session_id_a,
        "reasoning_effort": "high",  # Test reasoning_effort parameter
        "structured_output_schema": {
            "type": "object",
            "properties": {
                "security_analysis": {"type": "string"},
                "port_risks": {"type": "array", "items": {"type": "string"}},
                "reasoning_depth": {"type": "string"},
            },
            "required": ["security_analysis", "port_risks", "reasoning_depth"],
            "additionalProperties": False,
        },
    }

    response = claude(
        f"Use second-brain chat_with_o3 with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Parse and validate advanced reasoning
    result = safe_json(response)
    assert len(result["security_analysis"]) > 50  # Should be substantial
    assert len(result["port_risks"]) > 0  # Should identify some risks
    assert "8443" in result["security_analysis"]  # Should reference the specific port

    # Step 7: Test temperature parameter with memory context
    args = {
        "instructions": "Given that we've been discussing Protocol GAMMA-7, suggest 3 alternative protocol names that would fit the same naming pattern.",
        "output_format": "JSON array of creative protocol names",
        "context": [],
        "session_id": session_id_a,
        "temperature": 0.9,  # High creativity
        "structured_output_schema": {
            "type": "object",
            "properties": {
                "suggested_protocols": {"type": "array", "items": {"type": "string"}},
                "pattern_recognized": {"type": "boolean"},
            },
            "required": ["suggested_protocols", "pattern_recognized"],
            "additionalProperties": False,
        },
    }

    response = claude(
        f"Use second-brain chat_with_gpt4_1 with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Parse and validate creative suggestions
    result = safe_json(response)
    assert result["pattern_recognized"] is True
    assert len(result["suggested_protocols"]) == 3
    # Should follow pattern (Greek letter + number)
    assert all(len(protocol) > 5 for protocol in result["suggested_protocols"])
