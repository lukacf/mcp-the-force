"""Tool blueprints for OpenAI models."""

from mcp_the_force.tools.blueprint import ToolBlueprint
from mcp_the_force.tools.blueprint_registry import register_blueprints
from ..params import OpenAIToolParams
from .models import OPENAI_MODEL_CAPABILITIES

# Generate blueprints from model capabilities
blueprints = []

for model_name, capabilities in OPENAI_MODEL_CAPABILITIES.items():
    # Determine tool type based on model name
    if "deep-research" in model_name:
        tool_type = "research"
        timeout = 3600  # 1 hour for deep research
    else:
        tool_type = "chat"
        timeout = 300  # 5 minutes for regular chat

    blueprint = ToolBlueprint(
        model_name=model_name,
        adapter_key="openai",
        param_class=OpenAIToolParams,
        description=capabilities.description,
        timeout=timeout,
        context_window=capabilities.max_context_window or 200_000,
        tool_type=tool_type,
    )
    blueprints.append(blueprint)

# Self-register blueprints
register_blueprints(blueprints)
