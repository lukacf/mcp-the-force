"""Unit tests for capability-based tool generation and validation."""

import pytest
from mcp_the_force.tools.registry import get_tool
from mcp_the_force.tools.descriptors import RouteDescriptor, RouteType
from mcp_the_force.tools.base import ToolSpec


# Tool names as they appear in the registry
OPENAI_TOOL_NAMES = ["chat_with_o3", "chat_with_o3_pro", "chat_with_gpt41"]
GEMINI_TOOL_NAMES = ["chat_with_gemini25_pro", "chat_with_gemini25_flash"]
GROK_TOOL_NAMES = ["chat_with_grok4", "chat_with_grok3_beta"]
ALL_CHAT_TOOL_NAMES = OPENAI_TOOL_NAMES + GEMINI_TOOL_NAMES + GROK_TOOL_NAMES


class TestCapabilityBasedGeneration:
    """Test that tools are correctly generated based on adapter capabilities."""

    def test_all_generated_tools_inherit_base_params(self):
        """Verify that all dynamically generated tools have the base parameters."""
        for tool_name in ALL_CHAT_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None, f"Tool {tool_name} not found in registry"

            # Get the parameter class from the tool
            param_class = tool_metadata.spec_class
            # Verify it inherits from BaseToolParams
            assert issubclass(
                param_class, ToolSpec
            ), f"{tool_name}'s param class does not inherit from ToolSpec"

            # Check base parameters exist
            assert hasattr(param_class, "instructions")
            assert hasattr(param_class, "output_format")
            assert hasattr(param_class, "context")
            assert hasattr(param_class, "session_id")

    def test_reasoning_effort_is_capability_driven(self):
        """Verify reasoning_effort parameter has requires_capability check."""
        for tool_name in ALL_CHAT_TOOL_NAMES:
            metadata = get_tool(tool_name)
            assert metadata is not None

            # Check if the parameter exists on the tool's parameter class
            if hasattr(metadata.spec_class, "reasoning_effort"):
                # If the parameter exists, it should have a requires_capability check
                attr = getattr(metadata.spec_class, "reasoning_effort")
                if isinstance(attr, RouteDescriptor):
                    # The parameter should be filtered at runtime based on capabilities
                    assert hasattr(
                        attr, "requires_capability"
                    ), f"{tool_name}.reasoning_effort should have requires_capability check"
                    # If the model doesn't support it, the executor will filter it out
                    # This is the correct behavior for capability-based filtering

    def test_temperature_parameter_exists_on_all_tools(self):
        """Temperature should exist on all tools as it's universally supported."""
        for tool_name in ALL_CHAT_TOOL_NAMES:
            metadata = get_tool(tool_name)
            assert metadata is not None

            # Temperature is a universal parameter
            assert hasattr(
                metadata.spec_class, "temperature"
            ), f"{tool_name} missing temperature parameter"

    def test_correct_adapter_assignment(self):
        """Verify tools are assigned to the correct adapter families."""
        adapter_mappings = {
            "openai": OPENAI_TOOL_NAMES,
            "google": GEMINI_TOOL_NAMES,
            "xai": GROK_TOOL_NAMES,
        }

        for adapter_type, tool_names in adapter_mappings.items():
            for tool_name in tool_names:
                metadata = get_tool(tool_name)
                assert metadata is not None
                assert (
                    metadata.model_config.get("adapter_class") == adapter_type
                ), f"{tool_name} should use {adapter_type} adapter"

    def test_route_types_are_correct(self):
        """Verify parameters have the correct route types."""
        expected_routes = {
            "instructions": RouteType.PROMPT,
            "output_format": RouteType.PROMPT,
            "context": RouteType.PROMPT,
            "session_id": RouteType.SESSION,
            "temperature": RouteType.ADAPTER,
            "reasoning_effort": RouteType.ADAPTER,  # when it exists
        }

        for tool_name in ALL_CHAT_TOOL_NAMES:
            metadata = get_tool(tool_name)
            assert metadata is not None

            tool_class = metadata.spec_class

            for param_name, expected_route in expected_routes.items():
                if hasattr(tool_class, param_name):
                    attr = getattr(tool_class, param_name)
                    if isinstance(attr, RouteDescriptor):
                        assert attr.route == expected_route, (
                            f"{tool_name}.{param_name} has wrong route type: "
                            f"expected {expected_route}, got {attr.route}"
                        )

    def test_no_duplicate_parameter_positions(self):
        """No model should have duplicate position numbers for parameters."""
        for tool_name in ALL_CHAT_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None

            tool_class = tool_metadata.spec_class
            positions_used = {}

            for name in dir(tool_class):
                if name.startswith("_"):
                    continue
                attr = getattr(tool_class, name)
                if (
                    isinstance(attr, RouteDescriptor)
                    and hasattr(attr, "position")
                    and attr.position is not None
                ):
                    pos = attr.position
                    if pos in positions_used:
                        pytest.fail(
                            f"{tool_name}: Position {pos} used by both "
                            f"'{positions_used[pos]}' and '{name}'"
                        )
                    positions_used[pos] = name

    def test_all_tools_have_metadata(self):
        """All tools should have proper metadata."""
        for tool_name in ALL_CHAT_TOOL_NAMES:
            metadata = get_tool(tool_name)
            assert metadata is not None

            # Check required metadata fields
            assert (
                metadata.model_config.get("description") is not None
            ), f"{tool_name} missing description"
            assert (
                metadata.model_config.get("adapter_class") is not None
            ), f"{tool_name} missing adapter_class"
            assert (
                metadata.capabilities is not None
            ), f"{tool_name} missing capabilities"

    def test_web_search_capability_consistency(self):
        """Verify web search parameters match capabilities."""
        for tool_name in ALL_CHAT_TOOL_NAMES:
            metadata = get_tool(tool_name)
            assert metadata is not None

            # Check if web search OR live search is supported
            # Grok uses Live Search, OpenAI uses web_search
            supports_web_search = metadata.capabilities.supports_web_search
            supports_live_search = getattr(
                metadata.capabilities, "supports_live_search", False
            )
            supports_any_search = supports_web_search or supports_live_search

            # These parameters should only exist if some form of search is supported
            web_search_params = ["search_mode", "search_parameters", "return_citations"]

            for param in web_search_params:
                has_param = hasattr(metadata.spec_class, param)
                if has_param and not supports_any_search:
                    pytest.fail(
                        f"{tool_name} has {param} but doesn't support web search or live search"
                    )

    def test_disable_memory_params_exist(self):
        """All tools should have memory control parameters."""
        memory_params = ["disable_history_search", "disable_history_record"]

        for tool_name in ALL_CHAT_TOOL_NAMES:
            metadata = get_tool(tool_name)
            assert metadata is not None

            for param in memory_params:
                assert hasattr(
                    metadata.spec_class, param
                ), f"{tool_name} missing {param} parameter"
