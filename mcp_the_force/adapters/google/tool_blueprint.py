"""Tool blueprints for Google Gemini models."""

from mcp_the_force.tools.blueprint import ToolBlueprint
from mcp_the_force.tools.blueprint_registry import register_blueprints
from ..params import GeminiToolParams
from .models import GEMINI_MODEL_CAPABILITIES

# Generate blueprints from model capabilities
blueprints = []

for model_name, capabilities in GEMINI_MODEL_CAPABILITIES.items():
    # Set timeout based on model
    if "flash" in model_name:
        timeout = 300  # 5 minutes for flash
    elif "pro" in model_name:
        timeout = 480  # 8 minutes for pro
    else:
        timeout = 300  # Default 5 minutes

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
