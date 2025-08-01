import sys
import pytest

from mcp_the_force.tools.registry import list_tools, TOOL_REGISTRY


@pytest.mark.integration
def test_missing_openai_api_key_hides_tools(monkeypatch):
    """
    Given no OpenAI API key is configured,
    When the tool registry is initialized,
    Then OpenAI-based tools should not be available.
    """
    # Save original registry state
    original_registry = TOOL_REGISTRY.copy()

    # Cleanup function to restore registry
    def cleanup():
        TOOL_REGISTRY.clear()
        TOOL_REGISTRY.update(original_registry)

    monkeypatch.setattr("tests.integration.test_tool_loading._cleanup", cleanup)

    # Unload the autogen module to prevent premature tool registration
    monkeypatch.delitem(sys.modules, "mcp_the_force.tools.autogen", raising=False)

    # Clear the tool registry to ensure a clean state
    TOOL_REGISTRY.clear()

    # Register cleanup
    monkeypatch.undo = cleanup

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


@pytest.mark.integration
def test_openai_api_key_enables_tools(monkeypatch):
    """
    Given an OpenAI API key is configured,
    When the tool registry is initialized,
    Then OpenAI-based tools should be available.
    """
    # Save original registry state
    original_registry = TOOL_REGISTRY.copy()

    # Cleanup function to restore registry
    def cleanup():
        TOOL_REGISTRY.clear()
        TOOL_REGISTRY.update(original_registry)

    # Unload the autogen module to prevent premature tool registration
    monkeypatch.delitem(sys.modules, "mcp_the_force.tools.autogen", raising=False)

    # Clear the tool registry to ensure a clean state
    TOOL_REGISTRY.clear()

    # Register cleanup
    monkeypatch.undo = cleanup

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
