"""Auto-generate tool classes from adapter blueprints.

This module imports adapter packages which triggers blueprint registration
through their definitions.py files. It uses the central adapter registry
to know which adapters to import.
"""

import importlib
import logging

from .blueprint_registry import BLUEPRINTS
from .factories import make_tool
from ..adapters.registry import list_adapters

logger = logging.getLogger(__name__)

# Import all adapter packages from the central registry
# This ensures we have only ONE place where adapters are listed
for adapter_key in list_adapters():
    package = f"mcp_the_force.adapters.{adapter_key}"
    try:
        importlib.import_module(package)
        logger.debug(f"Imported adapter package: {package}")
    except ImportError as e:
        logger.warning(f"Failed to import adapter package {package}: {e}")

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
