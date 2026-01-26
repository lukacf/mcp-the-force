"""Test that tools are actually registered when server starts."""

import importlib
import sys


class TestToolRegistration:
    """Test tool registration flow."""

    def test_tools_are_registered_on_import(self):
        """Test that importing the server registers all tools."""
        # Just import and check - don't try to manipulate module state
        # as other tests may have already imported these modules
        from mcp_the_force import server  # noqa: F401
        from mcp_the_force.tools.registry import list_tools

        # Check tools are registered
        tools = list_tools()

        # We expect at least 5 model tools
        expected_tools = [
            "chat_with_gemini3_pro_preview",
            "chat_with_gemini3_flash_preview",
            "chat_with_gpt52_pro",
            "chat_with_gpt41",
            "chat_with_gpt51_codex_max",
        ]

        for tool_name in expected_tools:
            assert tool_name in tools, f"Tool {tool_name} not registered"

        # Verify each tool has proper metadata
        for tool_id, metadata in tools.items():
            if tool_id == metadata.id:  # Skip aliases
                # Local services have service_cls instead of adapter_class
                if metadata.model_config.get("service_cls"):
                    # This is a local service, different validation
                    assert metadata.model_config[
                        "model_name"
                    ], f"Tool {tool_id} missing model_name"
                else:
                    # This is an AI model tool
                    assert metadata.model_config[
                        "model_name"
                    ], f"Tool {tool_id} missing model_name"
                    assert metadata.model_config[
                        "adapter_class"
                    ], f"Tool {tool_id} missing adapter_class"
                # Description might be optional for test tools
                if not (
                    tool_id.startswith("test_")
                    or tool_id.startswith("tool")
                    or tool_id == "my_tool"
                ):
                    assert metadata.model_config.get(
                        "description"
                    ), f"Tool {tool_id} missing description"
                # Some utility tools (like setup_claude_code) are parameterless
                if tool_id not in ("setup_claude_code",):
                    assert (
                        len(metadata.parameters) > 0
                    ), f"Tool {tool_id} has no parameters"

    def test_no_duplicate_registrations(self):
        """Test that multiple imports don't duplicate tool registrations."""
        from mcp_the_force import server  # noqa: F401
        from mcp_the_force.tools.registry import list_tools

        # Get initial count
        tools_before = list_tools()
        primary_tools_before = [t for t, m in tools_before.items() if t == m.id]

        # Force reimport
        importlib.reload(sys.modules["mcp_the_force.server"])

        # Check count hasn't changed
        tools_after = list_tools()
        primary_tools_after = [t for t, m in tools_after.items() if t == m.id]

        assert len(primary_tools_before) == len(
            primary_tools_after
        ), "Tool count changed after reimport"
