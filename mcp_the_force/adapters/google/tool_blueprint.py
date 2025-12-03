"""Tool blueprints for Google Gemini models."""

from mcp_the_force.tools.blueprint import ToolBlueprint
from mcp_the_force.tools.blueprint_registry import register_blueprints
from .definitions import GeminiToolParams, GEMINI_MODEL_CAPABILITIES

# Generate blueprints from model capabilities
blueprints = []

for model_name, capabilities in GEMINI_MODEL_CAPABILITIES.items():
    # Set timeout based on model
    if "flash" in model_name:
        timeout = 600  # 10 minutes for flash (fast models)
    elif "pro" in model_name:
        timeout = 1800  # 30 minutes for pro (heavyweight models)
    else:
        timeout = 1800  # Default 30 minutes

    blueprint = ToolBlueprint(
        model_name=model_name,
        adapter_key="google",
        param_class=GeminiToolParams,
        description=capabilities.description,
        timeout=timeout,
        context_window=capabilities.max_context_window or 1_000_000,
        tool_type="chat",  # All Gemini models are chat tools
    )
    blueprints.append(blueprint)

# Self-register blueprints
register_blueprints(blueprints)
