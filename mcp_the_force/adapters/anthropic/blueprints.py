"""Tool blueprints for Anthropic Claude models."""

from typing import List

from ...tools.blueprint import ToolBlueprint
from ...tools.blueprint_registry import register_blueprints
from .capabilities import ANTHROPIC_MODEL_CAPABILITIES
from .params import AnthropicToolParams
from ...utils.capability_formatter import format_capabilities


def _get_friendly_name(model_name: str) -> str:
    """Generate a friendly tool name from the model name.

    Examples:
    - 'claude-sonnet-4-5' -> 'chat_with_claude45_sonnet'
    - 'claude-opus-4-5' -> 'chat_with_claude45_opus'
    """
    parts = model_name.split("-")

    # Handle claude-{variant}-4-5 pattern
    if len(parts) >= 4 and parts[0] == "claude" and parts[2] == "4" and parts[3] == "5":
        # claude-sonnet-4-5 -> claude45_sonnet
        variant = parts[1]  # sonnet, opus, haiku
        return f"chat_with_claude45_{variant}"

    # Fallback: join with underscores
    result = model_name.replace("-", "_")
    return f"chat_with_{result}"


def get_anthropic_blueprints() -> List[ToolBlueprint]:
    """Generate tool blueprints for all Anthropic models."""
    blueprints = []

    for model_name, capabilities in ANTHROPIC_MODEL_CAPABILITIES.items():
        tool_name = _get_friendly_name(model_name)

        # Format capabilities and append to description
        capability_info = format_capabilities(capabilities)
        full_description = capabilities.description
        if capability_info:
            full_description = f"{capabilities.description} [{capability_info}]"

        blueprint = ToolBlueprint(
            model_name=model_name,
            tool_name=tool_name,
            adapter_key="anthropic",
            param_class=AnthropicToolParams,
            description=full_description,
            timeout=1800,  # 30 minutes for heavyweight reasoning models
            context_window=capabilities.max_context_window
            or 200_000,  # All Anthropic models have 200k context
            tool_type="chat",  # All Anthropic models are chat tools
            cli="claude",  # All Anthropic models use Claude CLI
        )
        blueprints.append(blueprint)

    return blueprints


# Auto-register blueprints when this module is imported
_blueprints = get_anthropic_blueprints()
register_blueprints(_blueprints)

# Export for compatibility
BLUEPRINTS = _blueprints
