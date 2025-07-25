"""Tool blueprints for xAI Grok models."""

from mcp_the_force.tools.blueprint import ToolBlueprint
from mcp_the_force.tools.blueprint_registry import register_blueprints
from ..params import GrokToolParams
from .models import GROK_MODEL_CAPABILITIES

# Generate blueprints from model capabilities
blueprints = []

# Only generate tools for specific Grok models that are exposed to users
# We'll focus on the main models: grok-3-beta (reasoning) and grok-4 (advanced)
user_facing_models = {
    "grok-3-beta": "Deep reasoning using xAI Grok 3 Beta model (131k context)",
    "grok-4": "Advanced assistant using xAI Grok 4 model (256k context, multi-agent reasoning)",
}

for model_name, custom_description in user_facing_models.items():
    capabilities = GROK_MODEL_CAPABILITIES[model_name]

    blueprint = ToolBlueprint(
        model_name=model_name,
        adapter_key="xai",
        param_class=GrokToolParams,
        description=custom_description,  # Use custom description for clarity
        timeout=300,  # 5 minutes for all Grok models
        context_window=capabilities.max_context_window,
        tool_type="chat",  # All Grok models are chat tools
    )
    blueprints.append(blueprint)

# Self-register blueprints
register_blueprints(blueprints)
