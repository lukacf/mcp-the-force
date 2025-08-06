"""Tool blueprints for Anthropic Claude models."""

from typing import List

from ...tools.blueprint import ToolBlueprint
from ...tools.blueprint_registry import register_blueprints
from .capabilities import ANTHROPIC_MODEL_CAPABILITIES
from .params import AnthropicToolParams


def _get_friendly_name(model_name: str) -> str:
    """Generate a friendly tool name from the model name.

    Examples:
    - 'claude-3-opus' -> 'chat_with_claude3_opus'
    - 'claude-opus-4-0' -> 'chat_with_claude4_opus'
    - 'claude-sonnet-4-0' -> 'chat_with_claude4_sonnet'
    - 'claude-opus-4-1-20250805' -> 'chat_with_claude41_opus'
    """
    # Remove -0 suffix if present
    if model_name.endswith("-0"):
        model_name = model_name[:-2]

    parts = model_name.split("-")

    # Handle different naming patterns
    if len(parts) >= 3:
        if parts[0] == "claude" and parts[1].isdigit():
            # Pattern: claude-3-opus -> claude3_opus
            result = f"{parts[0]}{parts[1]}_{parts[2]}"
        elif (
            parts[0] == "claude"
            and parts[2] == "4"
            and parts[3] == "1"
            and len(parts) >= 5
        ):
            # Pattern: claude-opus-4-1-20250805 -> claude41_opus
            result = f"{parts[0]}{parts[2]}{parts[3]}_{parts[1]}"
        elif parts[0] == "claude" and parts[2] == "4":
            # Pattern: claude-opus-4 -> claude4_opus
            result = f"{parts[0]}{parts[2]}_{parts[1]}"
        else:
            # Fallback: join with underscores
            result = "_".join(parts)
    else:
        result = "_".join(parts)

    return f"chat_with_{result}"


def get_anthropic_blueprints() -> List[ToolBlueprint]:
    """Generate tool blueprints for all Anthropic models."""
    blueprints = []

    for model_name, capabilities in ANTHROPIC_MODEL_CAPABILITIES.items():
        blueprint = ToolBlueprint(
            model_name=model_name,
            tool_name=_get_friendly_name(model_name),
            adapter_key="anthropic",
            param_class=AnthropicToolParams,
            description=capabilities.description,
            timeout=600,  # 10 minutes default timeout
            context_window=capabilities.max_context_window
            or 200_000,  # All Anthropic models have 200k context
            tool_type="chat",  # All Anthropic models are chat tools
        )
        blueprints.append(blueprint)

    return blueprints


# Auto-register blueprints when this module is imported
_blueprints = get_anthropic_blueprints()
register_blueprints(_blueprints)

# Export for compatibility
BLUEPRINTS = _blueprints
