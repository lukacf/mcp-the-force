"""Auto-generate tool classes from adapter blueprints."""

import importlib
import logging

from .blueprint_registry import BLUEPRINTS
from .factories import make_tool

logger = logging.getLogger(__name__)

# Explicit list of blueprint modules
_BLUEPRINT_MODULES = [
    "mcp_the_force.adapters.openai.tool_blueprint",
    "mcp_the_force.adapters.google.tool_blueprint",
    "mcp_the_force.adapters.xai.tool_blueprint",
]

# Import all blueprint modules (triggers self-registration)
for modpath in _BLUEPRINT_MODULES:
    try:
        importlib.import_module(modpath)
        logger.debug(f"Imported blueprint module: {modpath}")
    except ImportError as e:
        logger.warning(f"Failed to import blueprint module {modpath}: {e}")

# Generate tool classes
generated_tools = []
for blueprint in BLUEPRINTS:
    try:
        tool_class = make_tool(blueprint)
        generated_tools.append(tool_class)
        logger.debug(
            f"Generated tool: {tool_class.__name__} for model {blueprint.model_name}"
        )
    except Exception as e:
        logger.error(f"Failed to generate tool for {blueprint.model_name}: {e}")

# Export generated tools for debugging/testing
__all__ = ["generated_tools"]
