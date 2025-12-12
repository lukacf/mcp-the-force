import sys
import pytest

from mcp_the_force.tools.registry import list_tools, TOOL_REGISTRY


@pytest.mark.integration
def test_missing_openai_api_key_hides_tools(request, monkeypatch):
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

    # Register cleanup to run after test
    request.addfinalizer(cleanup)

    # Unload the autogen module and adapter definitions to prevent premature tool registration
    monkeypatch.delitem(sys.modules, "mcp_the_force.tools.autogen", raising=False)
    monkeypatch.delitem(
        sys.modules, "mcp_the_force.adapters.openai.definitions", raising=False
    )

    # Also clear any other adapter modules that might be cached
    for module_name in list(sys.modules.keys()):
        if "mcp_the_force.adapters" in module_name and "definitions" in module_name:
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    # Clear the tool registry to ensure a clean state
    TOOL_REGISTRY.clear()

    # Remove any OpenAI API key to ensure OpenAI tools are not loaded
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MCP_OPENAI_API_KEY", raising=False)

    # Reload the settings to reflect the change
    from mcp_the_force.config import get_settings

    get_settings.cache_clear()

    # Re-import the autogen module to trigger tool registration
    import mcp_the_force.tools.autogen  # noqa: F401

    # List available tools
    available_tools = list_tools()

    # Assert that OpenAI tools are not in the registry
    assert "chat_with_gpt52" not in available_tools


@pytest.mark.integration
def test_openai_api_key_enables_tools(request, monkeypatch):
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

    # Register cleanup to run after test
    request.addfinalizer(cleanup)

    # Unload the autogen module and adapter definitions to prevent premature tool registration
    monkeypatch.delitem(sys.modules, "mcp_the_force.tools.autogen", raising=False)
    monkeypatch.delitem(
        sys.modules, "mcp_the_force.adapters.openai.definitions", raising=False
    )

    # Also clear any other adapter modules that might be cached
    for module_name in list(sys.modules.keys()):
        if "mcp_the_force.adapters" in module_name and "definitions" in module_name:
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    # Clear the tool registry to ensure a clean state
    TOOL_REGISTRY.clear()

    # Set the OPENAI_API_KEY environment variable
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")

    # Reload the settings to reflect the change
    from mcp_the_force.config import get_settings

    get_settings.cache_clear()

    # Re-import the autogen module to trigger tool registration
    import mcp_the_force.tools.autogen  # noqa: F401

    # List available tools
    available_tools = list_tools()

    # Assert that OpenAI tools are in the registry
    assert "chat_with_gpt52" in available_tools
