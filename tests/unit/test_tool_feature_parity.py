"""Unit tests to ensure feature parity across tool definitions."""

import pytest

from mcp_the_force.tools.registry import get_tool
from mcp_the_force.tools.descriptors import RouteDescriptor, RouteType


# Tool names as they appear in the registry
OPENAI_TOOL_NAMES = ["chat_with_o3", "chat_with_o3_pro", "chat_with_gpt41"]
REASONING_TOOL_NAMES = [
    "chat_with_o3",
    "chat_with_o3_pro",
]  # Only o3 models support reasoning
GEMINI_TOOL_NAMES = ["chat_with_gemini25_pro", "chat_with_gemini25_flash"]
GROK_TOOL_NAMES = ["chat_with_grok4", "chat_with_grok3_beta"]
ALL_CHAT_TOOL_NAMES = OPENAI_TOOL_NAMES + GEMINI_TOOL_NAMES + GROK_TOOL_NAMES

# Features that should be present in all chat models
REQUIRED_FEATURES = {
    "instructions": RouteType.PROMPT,
    "output_format": RouteType.PROMPT,
    "context": RouteType.PROMPT,
    "session_id": RouteType.SESSION,
}

# Optional features that should be consistent within model families
OPTIONAL_FEATURES = {
    "attachments": RouteType.VECTOR_STORE,
    "temperature": RouteType.ADAPTER,
}

# Model-specific features
OPENAI_SPECIFIC = {
    "reasoning_effort": RouteType.ADAPTER,
}


class TestToolFeatureParity:
    """Test that tool definitions have consistent features."""

    def test_all_models_have_required_features(self):
        """All chat models should have the required base features."""
        for tool_name in ALL_CHAT_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None, f"Tool {tool_name} not found in registry"

            tool_class = tool_metadata.spec_class

            for feature, expected_route_type in REQUIRED_FEATURES.items():
                # Check the attribute exists
                assert hasattr(tool_class, feature), (
                    f"{tool_name} missing required feature: {feature}"
                )

                # Check it's the right type of route
                attr = getattr(tool_class, feature)
                if isinstance(attr, RouteDescriptor):
                    assert attr.route == expected_route_type, (
                        f"{tool_name}.{feature} has wrong route type"
                    )

    def test_all_models_have_priority_context_support(self):
        """All chat models should support priority_context for prioritized inline inclusion."""
        # Skip this test - priority_context feature was removed in the new architecture
        pytest.skip("priority_context feature was removed in the new architecture")

    def test_reasoning_models_have_reasoning_effort(self):
        """O3 models should have reasoning_effort parameter."""
        for tool_name in REASONING_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None, f"Tool {tool_name} not found in registry"

            tool_class = tool_metadata.spec_class

            assert hasattr(tool_class, "reasoning_effort"), (
                f"{tool_name} missing reasoning_effort parameter"
            )

        # GPT-4.1 now also has reasoning_effort in the new architecture
        gpt41_metadata = get_tool("chat_with_gpt41")
        if gpt41_metadata:
            assert hasattr(gpt41_metadata.spec_class, "reasoning_effort"), (
                "chat_with_gpt41 should have reasoning_effort in the new architecture"
            )

    def test_gemini_models_have_reasoning_effort(self):
        """Gemini models should have reasoning_effort (now supported via thinking_budget)."""
        for tool_name in GEMINI_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None, f"Tool {tool_name} not found in registry"

            tool_class = tool_metadata.spec_class

            assert hasattr(tool_class, "reasoning_effort"), (
                f"{tool_name} should have reasoning_effort - Gemini now supports it via thinking_budget"
            )

    def test_all_models_have_descriptions(self):
        """All model tools should have descriptions."""
        for tool_name in ALL_CHAT_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None, f"Tool {tool_name} not found in registry"

            # Check the metadata has a description
            assert tool_metadata.model_config.get("description") is not None, (
                f"{tool_name} missing description"
            )

    def test_model_adapter_consistency(self):
        """Model should use the correct adapter family."""
        # Check Gemini models
        for tool_name in GEMINI_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None
            assert tool_metadata.model_config.get("adapter_class") == "google", (
                f"{tool_name} should use google adapter"
            )

        # Check OpenAI models
        for tool_name in OPENAI_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None
            assert tool_metadata.model_config.get("adapter_class") == "openai", (
                f"{tool_name} should use openai adapter"
            )

        # Check Grok models
        for tool_name in GROK_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None
            assert tool_metadata.model_config.get("adapter_class") == "xai", (
                f"{tool_name} should use xai adapter"
            )

    def test_no_duplicate_parameter_positions(self):
        """No model should have duplicate position numbers for parameters."""
        for tool_name in ALL_CHAT_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None, f"Tool {tool_name} not found in registry"

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

    def test_tools_are_dynamically_generated(self):
        """Verify that tools are dynamically generated and registered."""
        # Just check that we can get the tools from registry
        for tool_name in ALL_CHAT_TOOL_NAMES:
            tool_metadata = get_tool(tool_name)
            assert tool_metadata is not None, f"Tool {tool_name} not registered"
            assert tool_metadata.spec_class is not None, (
                f"Tool {tool_name} has no class"
            )
            assert tool_metadata.model_config.get("description") is not None, (
                f"Tool {tool_name} has no description"
            )
            assert tool_metadata.model_config.get("adapter_class") is not None, (
                f"Tool {tool_name} has no adapter type"
            )
