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
from ..config import get_settings

logger = logging.getLogger(__name__)


# Import all adapter packages from the central registry
# This ensures we have only ONE place where adapters are listed
settings = get_settings()
logger.debug(f"[AUTOGEN] Available adapters: {list_adapters()}")

for adapter_key in list_adapters():
    provider_config = getattr(settings, adapter_key, None)

    # Log the adapter config state for debugging
    if provider_config:
        logger.debug(
            f"[AUTOGEN] {adapter_key}: enabled={provider_config.enabled}, api_key_present={bool(provider_config.api_key)}"
        )
    else:
        logger.debug(f"[AUTOGEN] {adapter_key}: No provider config found")

    # Only skip if explicitly disabled - don't skip due to missing config or API keys
    if (
        provider_config
        and hasattr(provider_config, "enabled")
        and provider_config.enabled is False
    ):
        logger.info(f"[AUTOGEN] Skipping explicitly disabled adapter: {adapter_key}")
        continue

    package = f"mcp_the_force.adapters.{adapter_key}"
    try:
        importlib.import_module(package)
        logger.debug(f"[AUTOGEN] Successfully imported adapter package: {package}")
    except ImportError as e:
        logger.warning(f"[AUTOGEN] Failed to import adapter package {package}: {e}")
        continue

# Generate tool classes
logger.debug(f"[AUTOGEN] Found {len(BLUEPRINTS)} blueprints to process")
if len(BLUEPRINTS) == 0:
    logger.warning(
        "[AUTOGEN] No blueprints found! This means no model tools will be generated."
    )

generated_tools = []
for blueprint in BLUEPRINTS:
    try:
        tool_class = make_tool(blueprint)
        generated_tools.append(tool_class)
        logger.debug(
            f"[AUTOGEN] Generated tool: {tool_class.__name__} for model {blueprint.model_name}"
        )
    except Exception as e:
        logger.error(
            f"[AUTOGEN] Failed to generate tool for {blueprint.model_name}: {e}"
        )

logger.info(
    f"[AUTOGEN] Successfully generated {len(generated_tools)} tools from {len(BLUEPRINTS)} blueprints"
)

# Export generated tools for debugging/testing
__all__ = ["generated_tools"]
