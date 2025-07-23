"""JSON utility functions for E2E tests."""

import json
import re


def safe_json(response: str) -> dict:
    """
    Safely parse JSON from a response, handling various formats.

    Args:
        response: String that should contain JSON

    Returns:
        Parsed JSON object

    Raises:
        AssertionError: If no valid JSON found
    """
    # Try to parse the response directly first
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass

    # Look for JSON in code blocks (objects or arrays)
    json_pattern = r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```"
    match = re.search(json_pattern, response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Look for JSON objects in the text - improved regex for nested objects
    json_pattern = r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}"
    matches = re.findall(json_pattern, response, re.DOTALL)
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    # Try to find JSON starting with { and ending with }
    start = response.find("{")
    if start != -1:
        # Try different end positions to handle nested objects
        for end in range(len(response), start, -1):
            if response[end - 1] == "}":
                try:
                    return json.loads(response[start:end])
                except json.JSONDecodeError:
                    continue

    # If all parsing attempts fail
    assert False, f"No valid JSON found in response: {response}"


def extract_number(response: str) -> int:
    """
    Extract the first number from a response.

    Args:
        response: String that should contain a number

    Returns:
        First integer found in the response

    Raises:
        AssertionError: If no number found
    """
    numbers = re.findall(r"\d+", response)
    assert numbers, f"No numbers found in response: {response}"
    return int(numbers[0])
