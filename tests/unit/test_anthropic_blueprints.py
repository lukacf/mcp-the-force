"""Tests for Anthropic tool blueprints."""

from mcp_the_force.adapters.anthropic.blueprints import (
    get_anthropic_blueprints,
    BLUEPRINTS,
)
from mcp_the_force.adapters.anthropic.params import AnthropicToolParams


class TestAnthropicBlueprints:
    """Test Anthropic blueprint generation."""

    def test_blueprint_count(self):
        """Test that correct number of blueprints are generated."""
        blueprints = get_anthropic_blueprints()
        assert len(blueprints) == 3
        assert len(BLUEPRINTS) == 3

    def test_blueprint_names(self):
        """Test that blueprints have correct generated names."""
        blueprints = get_anthropic_blueprints()
        # Tool names are generated automatically by the blueprint system
        # Check model names instead
        model_names = [bp.model_name for bp in blueprints]

        # Check that we have the expected models
        assert "claude-4-opus" in model_names
        assert "claude-4-sonnet" in model_names
        assert "claude-3-opus" in model_names

    def test_blueprint_model_mapping(self):
        """Test that blueprints map to correct models."""
        blueprints = get_anthropic_blueprints()
        model_names = [bp.model_name for bp in blueprints]

        assert "claude-4-opus" in model_names
        assert "claude-4-sonnet" in model_names
        assert "claude-3-opus" in model_names

    def test_blueprint_adapter_key(self):
        """Test that all blueprints use anthropic adapter."""
        blueprints = get_anthropic_blueprints()
        for bp in blueprints:
            assert bp.adapter_key == "anthropic"

    def test_blueprint_param_class(self):
        """Test that all blueprints use AnthropicToolParams."""
        blueprints = get_anthropic_blueprints()
        for bp in blueprints:
            assert bp.param_class == AnthropicToolParams

    def test_blueprint_descriptions(self):
        """Test that blueprints have meaningful descriptions."""
        blueprints = get_anthropic_blueprints()
        for bp in blueprints:
            assert bp.description
            assert len(bp.description) > 10

        # Check specific descriptions
        opus4_bp = next(bp for bp in blueprints if bp.model_name == "claude-4-opus")
        assert "extended thinking" in opus4_bp.description
        assert "32k output" in opus4_bp.description

        sonnet4_bp = next(bp for bp in blueprints if bp.model_name == "claude-4-sonnet")
        assert "64k output" in sonnet4_bp.description

        opus3_bp = next(bp for bp in blueprints if bp.model_name == "claude-3-opus")
        assert "8k output" in opus3_bp.description

    def test_blueprint_capabilities(self):
        """Test that blueprints have proper capabilities."""
        _ = get_anthropic_blueprints()  # Verify blueprints can be generated

        # Get capabilities from the model capabilities dict
        from mcp_the_force.adapters.anthropic.capabilities import (
            ANTHROPIC_MODEL_CAPABILITIES,
        )

        opus4_caps = ANTHROPIC_MODEL_CAPABILITIES["claude-4-opus"]
        assert opus4_caps.supports_reasoning_effort is True
        assert opus4_caps.max_context_window == 200_000

        opus3_caps = ANTHROPIC_MODEL_CAPABILITIES["claude-3-opus"]
        assert opus3_caps.supports_reasoning_effort is False
