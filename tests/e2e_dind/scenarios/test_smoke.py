"""Smoke test - basic health check for all adapters."""

import logging

logger = logging.getLogger(__name__)


def test_smoke_all_models(claude, call_claude_tool, parse_response):
    """Test that all models respond to basic queries with structured output."""

    logger.info("=== SMOKE TEST: Basic adapter functionality ===")

    # Test 1: List available models
    logger.info("1. Testing list_models...")
    response = claude(
        "Use the-force list_models and return ONLY a JSON array of tool IDs (the 'id' field). "
        'Schema: {"tool_ids": ["string"]}. '
        'Example: {"tool_ids": ["chat_with_o3", "chat_with_gemini25_flash"]}'
    )

    # Parse the JSON response
    result = parse_response(response)
    assert result is not None, f"Failed to parse JSON from list_models: {response}"
    tool_ids = result.get("tool_ids", [])

    # Check that expected tools are present
    assert "chat_with_gpt41" in tool_ids, f"Missing chat_with_gpt41 in: {tool_ids}"
    assert (
        "chat_with_gemini25_flash" in tool_ids
    ), f"Missing chat_with_gemini25_flash in: {tool_ids}"
    assert "chat_with_o3" in tool_ids, f"Missing chat_with_o3 in: {tool_ids}"
    logger.info(f"✓ Model listing works, found {len(tool_ids)} tools")

    # Test all models with structured output
    math_schema = {
        "type": "object",
        "properties": {"result": {"type": "integer"}},
        "required": ["result"],
        "additionalProperties": False,
    }

    models_to_test = [
        ("chat_with_o3", "O3"),
        ("chat_with_gemini25_flash", "Gemini Flash"),
        ("chat_with_gemini25_pro", "Gemini Pro"),
        ("chat_with_gpt41", "GPT-4.1"),
        ("chat_with_grok4", "Grok"),
    ]

    for model_name, display_name in models_to_test:
        logger.info(f"Testing {display_name} with structured output...")
        response = call_claude_tool(
            model_name,
            response_format="respond with JSON only",
            instructions="What is 2 + 2?",
            output_format="JSON with result field containing the answer",
            context=[],
            session_id=f"smoke-{model_name}",
            structured_output_schema=math_schema,
        )

        # Parse and validate JSON response
        result = parse_response(response)
        assert (
            result is not None
        ), f"{display_name} didn't return valid JSON: {response}"
        assert result["result"] == 4, f"{display_name} gave wrong answer: {result}"
        logger.info(f"✓ {display_name} works with structured output")

    logger.info("=== All adapters working with structured output! ===")


def test_smoke_file_context(
    call_claude_tool, isolated_test_dir, create_file_in_container
):
    """Test that file context works with a simple unambiguous file."""

    logger.info("=== SMOKE TEST: File context ===")

    # Create a simple test file with unambiguous content
    test_file = f"{isolated_test_dir}/color.txt"
    file_content = "The color is RED."
    create_file_in_container(test_file, file_content)
    logger.info(f"Created test file: {test_file}")

    # Ask a simple question about the file
    response = call_claude_tool(
        "chat_with_gemini25_flash",
        instructions="What color is mentioned in the file?",
        output_format="Just the color name",
        context=[test_file],
        session_id="smoke-context",
    )

    assert "red" in response.lower()
    logger.info("✓ File context works")
