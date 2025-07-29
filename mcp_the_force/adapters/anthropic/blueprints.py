"""Tool blueprints for Anthropic Claude models."""

from typing import List

from ...tools.blueprint import ToolBlueprint
from .capabilities import ANTHROPIC_MODEL_CAPABILITIES
from .params import AnthropicToolParams


def get_anthropic_blueprints() -> List[ToolBlueprint]:
    """Generate tool blueprints for all Anthropic models."""
    blueprints = []

    for model_name, capabilities in ANTHROPIC_MODEL_CAPABILITIES.items():
        blueprint = ToolBlueprint(
            model_name=model_name,
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


# Export for auto-discovery
BLUEPRINTS = get_anthropic_blueprints()
