"""Lazy Adapter Registry for optimized startup performance."""

import importlib
import logging
from typing import Dict, Any, List

from ..adapters.registry import list_adapters

logger = logging.getLogger(__name__)


class LazyAdapterRegistry:
    """Registry that loads adapters only when first accessed."""

    def __init__(self):
        self._loaded_adapters: Dict[str, Any] = {}
        self._available_adapters = list_adapters()
        logger.info(
            f"Lazy registry initialized with {len(self._available_adapters)} available adapters"
        )

    def get_adapter(self, adapter_key: str) -> Any:
        """Load and return an adapter, loading it on first access."""
        if adapter_key not in self._loaded_adapters:
            if adapter_key not in self._available_adapters:
                raise ValueError(f"Unknown adapter: {adapter_key}")

            logger.info(f"Loading adapter on first use: {adapter_key}")
            package = f"mcp_the_force.adapters.{adapter_key}"

            try:
                self._loaded_adapters[adapter_key] = importlib.import_module(package)
                logger.debug(f"Successfully loaded adapter: {adapter_key}")
            except ImportError as e:
                logger.warning(f"Failed to load adapter {adapter_key}: {e}")
                raise

        return self._loaded_adapters[adapter_key]

    def is_loaded(self, adapter_key: str) -> bool:
        """Check if an adapter is already loaded."""
        return adapter_key in self._loaded_adapters

    def get_available_adapters(self) -> List[str]:
        """Get list of available adapters."""
        return self._available_adapters.copy()

    def get_loaded_adapters(self) -> List[str]:
        """Get list of currently loaded adapters."""
        return list(self._loaded_adapters.keys())


# Global lazy registry instance
_lazy_registry = LazyAdapterRegistry()


def get_adapter(adapter_key: str) -> Any:
    """Get an adapter using the lazy registry."""
    return _lazy_registry.get_adapter(adapter_key)


def get_available_adapters() -> List[str]:
    """Get available adapters without loading them."""
    return _lazy_registry.get_available_adapters()
