"""Debug test for GPT-4.1 issue."""


def test_debug_gpt41(claude):
    """Test direct Claude command to understand the issue."""

    print("\n=== DEBUG TEST: Checking MCP configuration ===")

    # First, list MCP servers
    response = claude("claude mcp list")
    print(f"MCP servers: {response}")

    # Try calling GPT-4.1 with a very simple command
    print("\n=== Testing simple GPT-4.1 call ===")
    response = claude(
        "Use the-force chat_with_gpt4_1 with instructions: 'Say hello', output_format: 'Just say hello', context: [], session_id: 'debug-test'"
    )
    print(f"Response: {response}")

    # Try without "the-force" prefix
    print("\n=== Testing without 'the-force' prefix ===")
    response = claude(
        "Use chat_with_gpt4_1 with instructions: 'Say hello', output_format: 'Just say hello', context: [], session_id: 'debug-test-2'"
    )
    print(f"Response: {response}")

    # Try listing models
    print("\n=== Testing list_models ===")
    response = claude("Use the-force list_models")
    print(f"Models: {response}")
