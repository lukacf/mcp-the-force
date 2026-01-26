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
        assert len(blueprints) == 2
        assert len(BLUEPRINTS) == 2

    def test_blueprint_names(self):
        """Test that blueprints have correct generated names."""
        blueprints = get_anthropic_blueprints()
        # Check model names
        model_names = [bp.model_name for bp in blueprints]
        assert "claude-opus-4-5" in model_names
        assert "claude-sonnet-4-5" in model_names

        # Check friendly tool names
        tool_names = [bp.tool_name for bp in blueprints]
        assert "chat_with_claude45_opus" in tool_names
        assert "chat_with_claude45_sonnet" in tool_names

    def test_blueprint_model_mapping(self):
        """Test that blueprints map to correct models."""
        blueprints = get_anthropic_blueprints()
        model_names = [bp.model_name for bp in blueprints]

        assert "claude-opus-4-5" in model_names
        assert "claude-sonnet-4-5" in model_names

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
        opus45_bp = next(bp for bp in blueprints if bp.model_name == "claude-opus-4-5")
        assert "premium maximum-intelligence" in opus45_bp.description
        assert (
            "max output: 64k tokens" in opus45_bp.description
        )  # From capability formatter

        sonnet45_bp = next(
            bp for bp in blueprints if bp.model_name == "claude-sonnet-4-5"
        )
        assert (
            "max output: 64k tokens" in sonnet45_bp.description
        )  # From capability formatter

    def test_blueprint_capabilities(self):
        """Test that blueprints have proper capabilities."""
        _ = get_anthropic_blueprints()  # Verify blueprints can be generated

        # Get capabilities from the model capabilities dict
        from mcp_the_force.adapters.anthropic.capabilities import (
            ANTHROPIC_MODEL_CAPABILITIES,
        )

        opus45_caps = ANTHROPIC_MODEL_CAPABILITIES["claude-opus-4-5"]
        assert opus45_caps.supports_reasoning_effort is True
        assert opus45_caps.max_context_window == 200_000

        sonnet45_caps = ANTHROPIC_MODEL_CAPABILITIES["claude-sonnet-4-5"]
        assert sonnet45_caps.supports_reasoning_effort is True
        assert sonnet45_caps.max_context_window == 1_000_000
