"""Dynamic blueprint generation for Ollama models."""

import asyncio
import logging
from typing import Dict, Optional

from ...config import get_settings as _original_get_settings
from ...tools.blueprint import ToolBlueprint
from ...tools.blueprint_registry import register_blueprints, unregister_blueprints
from ...tools.naming import model_to_chat_tool_name
from .discovery import list_models, discover_model_details
from .overrides import resolve_model_capabilities, ResolvedCapabilities
from .params import OllamaToolParams

logger = logging.getLogger(__name__)


# Helper to ensure we always get the current get_settings function
# This makes the code more testable by allowing late binding
def get_settings():
    """Get settings with late binding for better testability."""
    return _original_get_settings()


class OllamaBlueprints:
    """Manages dynamic blueprint generation for Ollama models."""

    def __init__(self):
        self._blueprints: Dict[str, ToolBlueprint] = {}
        self._capabilities: Dict[str, ResolvedCapabilities] = {}
        self._refresh_task: Optional[asyncio.Task] = None
        self._initialized = False

    async def initialize(self):
        """Initialize blueprint generator and start discovery."""
        if self._initialized:
            return

        settings = get_settings()
        if not settings.ollama.enabled:
            logger.info("Ollama integration disabled, skipping initialization")
            # Don't set _initialized = True when disabled
            return

        # Initial discovery
        if settings.ollama.discover_on_startup:
            await self.refresh()

        # Start periodic refresh if configured
        if settings.ollama.refresh_interval_sec > 0:
            self._refresh_task = asyncio.create_task(self._periodic_refresh())

        self._initialized = True

    async def refresh(self):
        """Discover models and generate/update blueprints."""
        settings = get_settings()
        cfg = settings.ollama

        if not cfg.enabled:
            return

        logger.info(f"Discovering Ollama models from {cfg.host}")

        try:
            # Discover available models
            models = await list_models(cfg.host)
            if not models:
                logger.warning("No Ollama models found")
                return

            logger.info(f"Found {len(models)} Ollama models")

            new_blueprints = {}
            new_capabilities = {}

            for model_info in models:
                name = model_info["name"]

                try:
                    # Get detailed model information
                    details = await discover_model_details(cfg.host, name)

                    # Resolve capabilities with overrides and memory constraints
                    caps = await resolve_model_capabilities(
                        name,
                        details,
                        cfg.context_overrides,
                        cfg.memory_aware_context,
                        cfg.memory_safety_margin,
                    )

                    # Create blueprint
                    tool_name = model_to_chat_tool_name(name)
                    bp = ToolBlueprint(
                        model_name=name,
                        adapter_key="ollama",
                        param_class=OllamaToolParams,
                        description=caps.description,
                        timeout=600,  # 10 minutes - local models can be slow
                        context_window=caps.max_context_window,
                        tool_type="chat",
                    )

                    new_blueprints[tool_name] = bp
                    new_capabilities[name] = caps

                    logger.info(
                        f"Registered {name}: {caps.max_context_window} tokens ({caps.source})"
                    )

                except Exception as e:
                    logger.error(f"Failed to process model {name}: {e}", exc_info=True)

            # Unregister removed models
            removed_tools = set(self._blueprints.keys()) - set(new_blueprints.keys())
            if removed_tools:
                removed_models = [
                    self._blueprints[tool].model_name
                    for tool in removed_tools
                    if tool in self._blueprints
                ]
                if removed_models:
                    unregister_blueprints(removed_models)
                    logger.info(
                        f"Unregistered {len(removed_models)} models: {', '.join(removed_models)}"
                    )

            # Register all current blueprints (registry will handle updates)
            if new_blueprints:
                register_blueprints(list(new_blueprints.values()))

            # Update internal state
            self._blueprints = new_blueprints
            self._capabilities = new_capabilities

            logger.info(
                f"Ollama blueprint refresh complete. "
                f"Active models: {', '.join(f'{n}:{c.max_context_window}' for n, c in new_capabilities.items())}"
            )

        except Exception as e:
            logger.error(f"Failed to refresh Ollama models: {e}", exc_info=True)

    async def _periodic_refresh(self):
        """Periodically refresh model list."""
        settings = get_settings()
        interval = settings.ollama.refresh_interval_sec

        while True:
            await asyncio.sleep(interval)
            try:
                await self.refresh()
            except Exception as e:
                logger.error(f"Periodic refresh failed: {e}")

    def get_capabilities(self) -> Dict[str, ResolvedCapabilities]:
        """Get current model capabilities."""
        return self._capabilities.copy()

    def shutdown(self):
        """Shutdown the blueprint generator."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            self._refresh_task = None
