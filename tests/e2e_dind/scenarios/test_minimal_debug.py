"""Minimal debug test to isolate E2E hanging issue."""

import logging

logger = logging.getLogger(__name__)


def test_minimal_debug_step1_list_tools(claude, parse_response):
    """Step 1: Test just tool listing - does this hang?"""
    logger.info("=== STEP 1: Testing tool listing ===")

    response = claude(
        'Use the-force list_models and return the output as JSON with structure {"tool_ids": ["tool1", "tool2"]}'
    )

    logger.info(f"✅ Tool listing completed: {len(response)} chars")
    result = parse_response(response)
    assert result is not None, f"Failed to parse JSON from list_models: {response}"
    assert "tool_ids" in result, f"Missing tool_ids in response: {result}"
    logger.info(f"✅ Found {len(result['tool_ids'])} tools")


def test_minimal_debug_step2_simple_call(claude, parse_response):
    """Step 2: Test one simple tool call - does this hang?"""
    logger.info("=== STEP 2: Testing simple tool call ===")

    response = claude(
        'Use the-force chat_with_gemini3_flash_preview with instructions: "Just say hello", output_format: "plain text", context: [], session_id: "debug-test-001"'
    )

    logger.info(f"✅ Simple tool call completed: {len(response)} chars")
    assert "hello" in response.lower(), f"Expected hello in response: {response}"
    logger.info("✅ Simple tool call works")


def test_minimal_debug_step3_structured_output(claude, parse_response):
    """Step 3: Test structured output - does this hang?"""
    logger.info("=== STEP 3: Testing structured output ===")

    response = claude(
        'Use the-force chat_with_gemini3_flash_preview with instructions: "Return a test result", output_format: "JSON with test_result field", context: [], session_id: "debug-test-002", structured_output_schema: {"type": "object", "properties": {"test_result": {"type": "string"}}, "required": ["test_result"]}'
    )

    logger.info(f"✅ Structured output completed: {len(response)} chars")
    result = parse_response(response)
    assert result is not None, f"Failed to parse JSON: {response}"
    assert "test_result" in result, f"Missing test_result: {result}"
    logger.info(f"✅ Structured output works: {result}")


def test_minimal_debug_step4_with_context(claude, parse_response):
    """Step 4: Test with context files - does this hang?"""
    logger.info("=== STEP 4: Testing with context files ===")

    response = claude(
        'Use the-force chat_with_gemini3_flash_preview with instructions: "Summarize the README", output_format: "brief summary", context: ["/host-project/README.md"], session_id: "debug-test-003"'
    )

    logger.info(f"✅ Context file test completed: {len(response)} chars")
    assert (
        "README" in response or "readme" in response.lower()
    ), f"Expected README mention: {response}"
    logger.info("✅ Context file test works")
