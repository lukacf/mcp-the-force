import sys

from mcp_the_force.tools.registry import list_tools, TOOL_REGISTRY


def test_missing_openai_api_key_hides_tools(monkeypatch):
    """
    Given no OpenAI API key is configured,
    When the tool registry is initialized,
    Then OpenAI-based tools should not be available.
    """
    # Unload the autogen module to prevent premature tool registration
    monkeypatch.delitem(sys.modules, "mcp_the_force.tools.autogen", raising=False)

    # Clear the tool registry to ensure a clean state
    TOOL_REGISTRY.clear()

    # Use a custom config file that disables the openai provider
    monkeypatch.setenv(
        "MCP_CONFIG_FILE",
        "/Users/luka/src/cc/gemini-vertex-improved/tests/integration/test_config.yaml",
    )

    # Reload the settings to reflect the change
    from mcp_the_force.config import get_settings

    get_settings.cache_clear()

    # Re-import the autogen module to trigger tool registration

    # List available tools
    available_tools = list_tools()

    # Assert that OpenAI tools are not in the registry
    assert "chat_with_o3" not in available_tools


def test_openai_api_key_enables_tools(monkeypatch):
    """
    Given an OpenAI API key is configured,
    When the tool registry is initialized,
    Then OpenAI-based tools should be available.
    """
    # Unload the autogen module to prevent premature tool registration
    monkeypatch.delitem(sys.modules, "mcp_the_force.tools.autogen", raising=False)

    # Clear the tool registry to ensure a clean state
    TOOL_REGISTRY.clear()

    # Set the OPENAI_API_KEY environment variable
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")

    # Reload the settings to reflect the change
    from mcp_the_force.config import get_settings

    get_settings.cache_clear()

    # Re-import the autogen module to trigger tool registration

    # List available tools
    available_tools = list_tools()

    # Assert that OpenAI tools are in the registry
    assert "chat_with_o3" in available_tools
