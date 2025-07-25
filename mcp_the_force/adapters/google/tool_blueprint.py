"""Tool blueprints for Google Gemini models."""

from mcp_the_force.tools.blueprint import ToolBlueprint
from mcp_the_force.tools.blueprint_registry import register_blueprints
from ..params import GeminiToolParams
from .models import GEMINI_MODEL_CAPABILITIES

# Generate blueprints from model capabilities
blueprints = []

for model_name, capabilities in GEMINI_MODEL_CAPABILITIES.items():
    blueprint = ToolBlueprint(
        model_name=model_name,
        adapter_key="google",
        param_class=GeminiToolParams,
        description=capabilities.description,
        timeout=300,  # 5 minutes for all Gemini models
        context_window=capabilities.max_context_window or 1_000_000,
        tool_type="chat",  # All Gemini models are chat tools
    )
    blueprints.append(blueprint)

# Self-register blueprints
register_blueprints(blueprints)
