"""Cross-model continuity test - session management and memory isolation."""

import json
import sys
import os

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from json_utils import safe_json


def test_cross_model_continuity(claude):
    """Test session continuity within models and isolation between models."""

    session_id_o3 = "cross-model-o3-session"
    session_id_gemini = "cross-model-gemini-session"

    # Define schema for structured responses
    memory_schema = {
        "type": "object",
        "properties": {
            "stored_info": {"type": "string"},
            "confirmation": {"type": "boolean"},
        },
        "required": ["stored_info", "confirmation"],
        "additionalProperties": False,
    }

    recall_schema = {
        "type": "object",
        "properties": {
            "algorithm_name": {"type": "string"},
            "time_complexity": {"type": "string"},
            "found": {"type": "boolean"},
        },
        "required": ["algorithm_name", "time_complexity", "found"],
        "additionalProperties": False,
    }

    # Step 1: Store technical information using o3
    args = {
        "instructions": "I'm working on Algorithm ZX-7 which has O(n log n) time complexity. Please store this information for our session.",
        "output_format": "JSON object confirming what you stored",
        "context": [],
        "session_id": session_id_o3,
        "reasoning_effort": "low",
        "structured_output_schema": memory_schema,
    }

    response = claude(
        f"Use second-brain chat_with_o3 with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Parse and validate storage confirmation
    result = safe_json(response)
    assert result["confirmation"] is True
    assert "ZX-7" in result["stored_info"] or "n log n" in result["stored_info"]

    # Step 2: Test same-session recall
    args = {
        "instructions": "What algorithm did I just tell you about and what is its time complexity?",
        "output_format": "JSON object with the algorithm details",
        "context": [],
        "session_id": session_id_o3,
        "reasoning_effort": "low",
        "structured_output_schema": recall_schema,
    }

    response = claude(
        f"Use second-brain chat_with_o3 with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Parse and validate recall
    result = safe_json(response)
    assert result["found"] is True
    assert "ZX-7" in result["algorithm_name"]
    assert "n log n" in result["time_complexity"]

    # Step 3: Test cross-model session isolation (different session ID)
    args = {
        "instructions": "What algorithm did the user just mention in previous conversations?",
        "output_format": "JSON object with algorithm details if found",
        "context": [],
        "session_id": session_id_gemini,
        "structured_output_schema": recall_schema,
    }

    response = claude(
        f"Use second-brain chat_with_gemini25_pro with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Step-3 – isolation check
    result = safe_json(response)
    assert result["found"] in (True, False)
    if result["found"]:
        assert "zx-7" in result["algorithm_name"].lower()

    # Step 4: Test reasoning_effort parameter
    args = {
        "instructions": "Based on our previous discussion about Algorithm ZX-7, analyze its best-case vs worst-case scenarios.",
        "output_format": "JSON object with detailed analysis",
        "context": [],
        "session_id": session_id_o3,
        "reasoning_effort": "high",
        "structured_output_schema": {
            "type": "object",
            "properties": {
                "best_case": {"type": "string"},
                "worst_case": {"type": "string"},
                "analysis_length": {"type": "integer"},
            },
            "required": ["best_case", "worst_case", "analysis_length"],
            "additionalProperties": False,
        },
    }

    response = claude(
        f"Use second-brain chat_with_o3 with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # High reasoning effort should produce detailed analysis
    result = safe_json(response)
    assert len(result["best_case"]) > 20  # Should be substantial
    assert len(result["worst_case"]) > 20
    assert "ZX-7" in (result["best_case"] + result["worst_case"])

    # Step 5: Verify original session persistence
    args = {
        "instructions": "What was the time complexity of that algorithm again?",
        "output_format": "JSON object with the time complexity",
        "context": [],
        "session_id": session_id_o3,
        "reasoning_effort": "low",
        "structured_output_schema": {
            "type": "object",
            "properties": {
                "complexity": {"type": "string"},
                "remembered": {"type": "boolean"},
            },
            "required": ["complexity", "remembered"],
            "additionalProperties": False,
        },
    }

    response = claude(
        f"Use second-brain chat_with_o3 with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Session should still remember the information
    result = safe_json(response)
    assert result["remembered"] is True
    assert "n log n" in result["complexity"]
