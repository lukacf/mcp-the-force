"""Tests for capability validator."""

import pytest
from typing import List
from dataclasses import dataclass

from mcp_the_force.tools.capability_validator import CapabilityValidator
from mcp_the_force.tools.registry import ParameterInfo, ToolMetadata
from mcp_the_force.tools.descriptors import RouteType
from mcp_the_force.adapters.capabilities import AdapterCapabilities


@dataclass
class MockCapabilities(AdapterCapabilities):
    """Mock capabilities for testing."""

    supports_vision: bool = False
    supports_temperature: bool = True


class TestCapabilityValidator:
    """Test capability validation logic."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return CapabilityValidator()

    @pytest.fixture
    def vision_param_info(self):
        """Parameter that requires vision capability."""
        return ParameterInfo(
            name="images",
            type=List[str],
            type_str="List[str]",
            route=RouteType.ADAPTER,
            position=None,
            default=None,
            required=False,
            description="Image paths",
            requires_capability=lambda c: c.supports_vision,
            default_factory=list,
        )

    @pytest.fixture
    def mock_metadata(self, vision_param_info):
        """Create mock tool metadata with vision parameter."""
        return ToolMetadata(
            id="test_tool",
            spec_class=object,  # type: ignore
            parameters={"images": vision_param_info},
            model_config={},
        )

    def test_skips_validation_for_empty_list_default(
        self, validator, mock_metadata, vision_param_info
    ):
        """Empty list should skip validation when default_factory=list."""
        capabilities = MockCapabilities(supports_vision=False)

        # Pass empty list (the default value from default_factory=list)
        kwargs = {"images": []}

        # Should not raise - empty list equals default_factory() result
        validator.validate_against_capabilities(mock_metadata, kwargs, capabilities)

    def test_skips_validation_for_none_value(
        self, validator, mock_metadata, vision_param_info
    ):
        """None value should skip validation."""
        capabilities = MockCapabilities(supports_vision=False)

        kwargs = {"images": None}

        # Should not raise - None is treated as empty
        validator.validate_against_capabilities(mock_metadata, kwargs, capabilities)

    def test_skips_validation_when_param_not_provided(
        self, validator, mock_metadata, vision_param_info
    ):
        """Missing parameter should skip validation."""
        capabilities = MockCapabilities(supports_vision=False)

        kwargs = {}  # images not provided

        # Should not raise - parameter not in kwargs
        validator.validate_against_capabilities(mock_metadata, kwargs, capabilities)

    def test_raises_for_non_empty_list_without_capability(
        self, validator, mock_metadata, vision_param_info
    ):
        """Non-empty list should raise when capability not supported."""
        capabilities = MockCapabilities(supports_vision=False)

        kwargs = {"images": ["/path/to/image.png"]}

        # Should raise because images is non-empty but vision not supported
        with pytest.raises(ValueError, match="not supported"):
            validator.validate_against_capabilities(mock_metadata, kwargs, capabilities)

    def test_passes_for_non_empty_list_with_capability(
        self, validator, mock_metadata, vision_param_info
    ):
        """Non-empty list should pass when capability is supported."""
        capabilities = MockCapabilities(supports_vision=True)

        kwargs = {"images": ["/path/to/image.png"]}

        # Should not raise because vision is supported
        validator.validate_against_capabilities(mock_metadata, kwargs, capabilities)

    def test_skips_validation_for_local_tools(self, validator, mock_metadata):
        """Local tools (capabilities=None) should skip all validation."""
        kwargs = {"images": ["/path/to/image.png"]}

        # Should not raise even with non-empty images when capabilities is None
        validator.validate_against_capabilities(mock_metadata, kwargs, None)

    def test_get_default_value_uses_default_factory(self, vision_param_info):
        """ParameterInfo.get_default_value() should use default_factory."""
        # default is None, but default_factory returns []
        assert vision_param_info.default is None
        assert vision_param_info.default_factory is not None
        assert vision_param_info.get_default_value() == []

    def test_get_default_value_returns_default_when_no_factory(self):
        """ParameterInfo.get_default_value() should return default when no factory."""
        param_info = ParameterInfo(
            name="temp",
            type=float,
            type_str="float",
            route=RouteType.ADAPTER,
            position=None,
            default=0.7,
            required=False,
            description="Temperature",
            default_factory=None,
        )

        assert param_info.get_default_value() == 0.7

    def test_infer_capability_name_from_lambda(self, validator):
        """_infer_capability_name should extract capability from lambda."""
        capabilities = MockCapabilities(
            supports_vision=False, supports_temperature=True
        )

        def capability_check(c):
            return c.supports_vision

        name = validator._infer_capability_name(capability_check, capabilities)
        assert name == "supports_vision"

    def test_infer_capability_name_with_multiple_false_capabilities(self, validator):
        """_infer_capability_name should list multiple False capabilities."""
        capabilities = MockCapabilities(
            supports_vision=False, supports_temperature=False
        )

        # Function that accesses a capability not in MockCapabilities
        # This forces fallback to listing all False capabilities
        def capability_check(c):
            return getattr(c, "supports_something_else", False)

        name = validator._infer_capability_name(capability_check, capabilities)
        # Should list multiple False capabilities (includes base class defaults)
        assert "supports_vision" in name or "supports_temperature" in name

    def test_validates_explicit_empty_list_when_default_is_none(self, validator):
        """Explicit empty list should validate when default is None (no factory)."""
        # Create parameter with default=None and NO default_factory
        param_info = ParameterInfo(
            name="images",
            type=List[str],
            type_str="List[str]",
            route=RouteType.ADAPTER,
            position=None,
            default=None,
            required=False,
            description="Image paths",
            requires_capability=lambda c: c.supports_vision,
            default_factory=None,  # No factory, so default is None
        )

        metadata = ToolMetadata(
            id="test_tool",
            spec_class=object,  # type: ignore
            parameters={"images": param_info},
            model_config={},
        )

        capabilities = MockCapabilities(supports_vision=False)

        # Pass explicit empty list - should validate because [] != None
        kwargs = {"images": []}

        # Should raise because we explicitly passed [] which is different from default None
        with pytest.raises(ValueError, match="not supported"):
            validator.validate_against_capabilities(metadata, kwargs, capabilities)
