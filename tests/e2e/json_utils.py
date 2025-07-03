"""JSON utilities for E2E tests."""

import json
import re
from typing import Any


def safe_json(raw: str) -> Any:
    """
    Best-effort JSON extractor that handles edge cases like empty responses,
    markdown code fences, and control characters.
    """
    if not raw or not raw.strip():
        raise AssertionError("Model returned an empty response")

    # Simple JSON parsing for now - can be enhanced if needed
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        # Try to extract JSON from markdown code fences
        cleaned = re.sub(r"```(?:json)?|```", "", raw, flags=re.I).strip()
        if cleaned:
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass
        raise AssertionError(f"Failed to parse JSON from response: {raw!r}, error: {e}")
