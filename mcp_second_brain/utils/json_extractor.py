"""Utility for extracting JSON from various response formats."""

import json
import re
from typing import Any


def extract_json(content: str) -> str:
    """Extract JSON from content that may be wrapped in markdown or other formatting.

    This handles cases where models return JSON wrapped in markdown code blocks
    despite structured output settings.

    Args:
        content: The response content that may contain JSON

    Returns:
        Clean JSON string ready for parsing

    Raises:
        ValueError: If no valid JSON can be extracted
    """
    if not content:
        raise ValueError("Empty content")

    # First, try to parse as-is (best case: already clean JSON)
    content = content.strip()
    try:
        json.loads(content)
        return content
    except json.JSONDecodeError:
        pass

    # Look for JSON in markdown code blocks (most common case)
    # Matches ```json ... ``` or ``` ... ```
    json_pattern = r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```"
    matches = re.findall(json_pattern, content, re.DOTALL | re.IGNORECASE)

    if matches:
        # Take the first match (usually there's only one)
        extracted = matches[0]
        try:
            json.loads(extracted)
            return str(extracted)
        except json.JSONDecodeError:
            pass

    # Look for JSON objects or arrays without code blocks
    # This is more permissive - finds any {...} or [...] structure
    object_pattern = r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})"
    array_pattern = r"(\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])"

    for pattern in [object_pattern, array_pattern]:
        matches = re.findall(pattern, content, re.DOTALL)
        for match in matches:
            try:
                json.loads(match)
                return str(match)
            except json.JSONDecodeError:
                continue

    # Last resort: try to find JSON-like content and clean it up
    # Remove common prefixes/suffixes that models might add
    cleaned = content
    for prefix in ["Here is the JSON:", "JSON:", "Output:", "Result:", "Response:"]:
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix) :].strip()
            break

    # Remove trailing text after JSON
    if cleaned.startswith("{") or cleaned.startswith("["):
        # Find the matching closing bracket
        bracket_count = 0
        end_pos = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(cleaned):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if not in_string:
                if char in "{[":
                    bracket_count += 1
                elif char in "}]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = i + 1
                        break

        if end_pos > 0:
            cleaned = cleaned[:end_pos]
            try:
                json.loads(cleaned)
                return cleaned
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Could not extract valid JSON from content: {content[:200]}...")


def parse_json_response(content: str) -> Any:
    """Parse JSON response, handling markdown wrapping and other formatting.

    Args:
        content: The response content that may contain JSON

    Returns:
        Parsed JSON object (dict, list, etc.)

    Raises:
        ValueError: If no valid JSON can be extracted
        json.JSONDecodeError: If extracted content is not valid JSON
    """
    clean_json = extract_json(content)
    return json.loads(clean_json)
