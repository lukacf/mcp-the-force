"""Smoke test - basic health check and simple chat."""

import json
import sys
import os

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from json_utils import safe_json


def test_smoke_health_and_simple_chat(claude):
    """Test server health, model listing, and structured outputs."""

    # Test 1: List available models
    response = claude(
        "Use second-brain list_models and respond with the exact output you receive."
    )

    # Should contain at least some of our models
    assert "chat_with_gpt4_1" in response
    assert "chat_with_gemini25_flash" in response
    assert "chat_with_o3" in response

    # Test 2: Simple mathematical reasoning with structured output
    math_schema = {
        "type": "object",
        "properties": {
            "calculation": {"type": "string"},
            "result": {"type": "integer"},
            "method": {"type": "string"},
        },
        "required": ["calculation", "result", "method"],
        "additionalProperties": False,
    }

    args = {
        "instructions": "Calculate 12 + 15 and explain your method",
        "output_format": "JSON object matching the provided schema",
        "context": [],
        "session_id": "smoke-math",
        "structured_output_schema": math_schema,
    }

    response = claude(
        f"Use second-brain chat_with_o3 with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Parse and validate structured response
    result = safe_json(response)
    assert result["result"] == 27
    assert "12" in result["calculation"] and "15" in result["calculation"]
    assert len(result["method"]) > 0

    # Test 3: Fast summarization task
    summary_schema = {
        "type": "object",
        "properties": {
            "main_topic": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "word_count": {"type": "integer"},
        },
        "required": ["main_topic", "key_points", "word_count"],
        "additionalProperties": False,
    }

    args = {
        "instructions": "Summarize this text: Python is a high-level programming language. It was created by Guido van Rossum. Python emphasizes code readability with its use of significant whitespace.",
        "output_format": "JSON object matching the provided schema",
        "context": [],
        "session_id": "smoke-summary",
        "structured_output_schema": summary_schema,
    }

    response = claude(
        f"Use second-brain chat_with_gemini25_flash with {json.dumps(args)} and respond ONLY with the JSON."
    )

    # Parse and validate structured response
    result = safe_json(response)
    assert "python" in result["main_topic"].lower()
    assert len(result["key_points"]) >= 2
    assert result["word_count"] > 0
