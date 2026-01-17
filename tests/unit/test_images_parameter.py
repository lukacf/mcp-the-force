"""Tests for images parameter in tool definitions - TDD."""

from typing import get_type_hints


class TestImagesParameterDefinition:
    """Test that images parameter is properly defined on BaseToolParams."""

    def test_images_parameter_exists(self):
        """BaseToolParams should have an images parameter."""
        from mcp_the_force.adapters.params import BaseToolParams
        from mcp_the_force.tools.descriptors import RouteDescriptor

        # The images attribute should be a RouteDescriptor
        assert hasattr(BaseToolParams, "images")
        assert isinstance(BaseToolParams.images, RouteDescriptor)

    def test_images_parameter_type_annotation(self):
        """images parameter should be typed as Optional[List[str]]."""
        from mcp_the_force.adapters.params import BaseToolParams

        hints = get_type_hints(BaseToolParams)
        assert "images" in hints

        # Should be Optional[List[str]]
        images_type = hints["images"]
        # Check it's Optional (contains None type)
        assert type(None) in getattr(images_type, "__args__", ())

    def test_images_parameter_has_default_empty_list(self):
        """images parameter should default to empty list."""
        from mcp_the_force.adapters.params import BaseToolParams

        params = BaseToolParams()
        assert params.images == []

    def test_images_parameter_requires_vision_capability(self):
        """images parameter should require supports_vision capability."""
        from mcp_the_force.adapters.params import BaseToolParams
        from mcp_the_force.tools.descriptors import RouteDescriptor

        images_descriptor: RouteDescriptor = BaseToolParams.images
        assert images_descriptor.requires_capability is not None

        # Test with vision-supporting capability
        class VisionCapable:
            supports_vision = True

        class NonVisionCapable:
            supports_vision = False

        # The capability check should pass for vision-capable models
        assert images_descriptor.requires_capability(VisionCapable()) is True
        assert images_descriptor.requires_capability(NonVisionCapable()) is False

    def test_images_parameter_has_description(self):
        """images parameter should have a descriptive help text."""
        from mcp_the_force.adapters.params import BaseToolParams
        from mcp_the_force.tools.descriptors import RouteDescriptor

        images_descriptor: RouteDescriptor = BaseToolParams.images
        assert images_descriptor.description is not None
        assert (
            len(images_descriptor.description) > 50
        )  # Should be a meaningful description


class TestImagesParameterExtraction:
    """Test that images parameter is properly extracted from tools."""

    def test_images_in_get_parameters(self):
        """Blueprint's param_class should include images parameter."""
        from mcp_the_force.tools.blueprint_registry import get_blueprints

        # Import definitions to trigger blueprint registration
        import mcp_the_force.adapters.google.definitions  # noqa: F401

        # Get a vision-capable model's blueprint
        blueprints = get_blueprints()
        blueprint = next(
            (b for b in blueprints if b.tool_name == "chat_with_gemini_3_pro_preview"),
            None,
        )
        assert (
            blueprint is not None
        ), f"Blueprint not found. Available: {[b.tool_name for b in blueprints]}"

        # Check that the param_class has the images parameter
        param_class = blueprint.param_class
        assert hasattr(
            param_class, "images"
        ), "param_class should have images attribute"

        # Verify it has the capability requirement
        from mcp_the_force.tools.descriptors import RouteDescriptor

        images_descriptor = param_class.images
        assert isinstance(images_descriptor, RouteDescriptor)
        assert images_descriptor.requires_capability is not None


class TestCapabilityEnforcement:
    """Test that images parameter respects capability validation."""

    def test_vision_capable_models_support_images(self):
        """Vision-capable models should support the images parameter."""
        from mcp_the_force.adapters.google.definitions import GeminiBaseCapabilities
        from mcp_the_force.adapters.anthropic.definitions import (
            AnthropicBaseCapabilities,
        )

        # Check that these models have vision support
        gemini_caps = GeminiBaseCapabilities()
        assert gemini_caps.supports_vision is True

        anthropic_caps = AnthropicBaseCapabilities()
        assert anthropic_caps.supports_vision is True

    def test_non_vision_models_do_not_support_images(self):
        """Non-vision models should not support images parameter."""
        from mcp_the_force.adapters.xai.definitions import GrokBaseCapabilities

        grok_caps = GrokBaseCapabilities()
        assert grok_caps.supports_vision is False
