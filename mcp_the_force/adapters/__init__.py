"""Adapter module for AI model integrations."""

from typing import Dict, Tuple, Type, Optional
from .base import BaseAdapter
from .openai import OpenAIAdapter
from .vertex import VertexAdapter
from .grok import GrokAdapter
from .grok_litellm import GrokLiteLLMAdapter
from .litellm import LiteLLMAdapter

# Protocol components imported lazily to avoid circular imports
import logging


logger = logging.getLogger(__name__)

# Adapter registry
ADAPTER_REGISTRY: Dict[str, Type[BaseAdapter]] = {
    "openai": OpenAIAdapter,
    "vertex": VertexAdapter,
    "xai": GrokAdapter,  # Old adapter (to be replaced)
    "xai_litellm": GrokLiteLLMAdapter,  # New LiteLLM-based adapter
    # "xai_protocol" registered dynamically below
    "litellm": LiteLLMAdapter,
}


# Adapter instance cache
_ADAPTER_CACHE: Dict[Tuple[str, str], BaseAdapter] = {}


def get_adapter(
    adapter_key: str, model_name: str
) -> Tuple[Optional[BaseAdapter], Optional[str]]:
    """Get or create an adapter instance.

    Args:
        adapter_key: Key identifying the adapter type (e.g., "openai", "vertex")
        model_name: Name of the model (e.g., "o3", "gemini-2.5-pro")

    Returns:
        Tuple of (adapter instance, error message)
    """
    # Check if we should use mock adapter
    from ..config import get_settings

    if get_settings().adapter_mock:
        # Use MockAdapter for all adapters when in mock mode
        from .mock_adapter import MockAdapter

        cache_key = (adapter_key, model_name)
        if cache_key in _ADAPTER_CACHE:
            return _ADAPTER_CACHE[cache_key], None

        adapter = MockAdapter(model_name)
        _ADAPTER_CACHE[cache_key] = adapter  # type: ignore[assignment]
        logger.debug(f"Created MockAdapter for {model_name} (adapter_mock=True)")
        return adapter, None

    # Lazy load search adapters to break circular imports
    if adapter_key == "SearchHistoryAdapter" and adapter_key not in ADAPTER_REGISTRY:
        try:
            from ..tools.search_history import SearchHistoryAdapter

            register_adapter("SearchHistoryAdapter", SearchHistoryAdapter)
            logger.debug("Lazily registered SearchHistoryAdapter")
        except ImportError as e:
            logger.error(f"Failed to lazy-load SearchHistoryAdapter: {e}")
            return (
                None,
                f"Adapter {adapter_key} could not be loaded due to an import error.",
            )
    if adapter_key == "SearchTaskFilesAdapter" and adapter_key not in ADAPTER_REGISTRY:
        try:
            from ..tools.search_task_files import SearchTaskFilesAdapter

            register_adapter("SearchTaskFilesAdapter", SearchTaskFilesAdapter)
            logger.debug("Lazily registered SearchTaskFilesAdapter")
        except ImportError as e:
            logger.error(f"Failed to lazy-load SearchTaskFilesAdapter: {e}")
            return (
                None,
                f"Adapter {adapter_key} could not be loaded due to an import error.",
            )
    if adapter_key == "LoggingAdapter" and adapter_key not in ADAPTER_REGISTRY:
        try:
            from .logging_adapter import LoggingAdapter

            register_adapter("LoggingAdapter", LoggingAdapter)
            logger.debug("Lazily registered LoggingAdapter")
        except ImportError as e:
            logger.error(f"Failed to lazy-load LoggingAdapter: {e}")
            return (
                None,
                f"Adapter {adapter_key} could not be loaded due to an import error.",
            )

    # Lazy load protocol-based Grok adapter
    if adapter_key == "xai_protocol" and adapter_key not in ADAPTER_REGISTRY:
        try:
            from .grok_bridge import GrokBridgeAdapter

            register_adapter("xai_protocol", GrokBridgeAdapter)
            logger.debug("Lazily registered GrokBridgeAdapter")
        except ImportError as e:
            logger.error(f"Failed to lazy-load GrokBridgeAdapter: {e}")
            return (
                None,
                f"Protocol adapter {adapter_key} could not be loaded: {e}",
            )

    cache_key = (adapter_key, model_name)

    # Check cache first
    if cache_key in _ADAPTER_CACHE:
        return _ADAPTER_CACHE[cache_key], None

    # Get adapter class
    adapter_class = ADAPTER_REGISTRY.get(adapter_key)
    if not adapter_class:
        return None, f"Unknown adapter: {adapter_key}"

    try:
        # Create adapter instance
        adapter = adapter_class(model_name)  # type: ignore
        _ADAPTER_CACHE[cache_key] = adapter  # type: ignore
        logger.debug(f"Created {adapter_key} adapter for {model_name}")
        return adapter, None
    except Exception as e:
        logger.error(f"Failed to create {adapter_key} adapter: {e}")
        return None, str(e)


def register_adapter(key: str, adapter_class: Type[BaseAdapter]):
    """Register a new adapter type.

    Args:
        key: Unique key for the adapter
        adapter_class: Adapter class that inherits from BaseAdapter
    """
    ADAPTER_REGISTRY[key] = adapter_class
    logger.debug(f"Registered adapter: {key}")


__all__ = [
    # Legacy adapters
    "BaseAdapter",
    "OpenAIAdapter",
    "VertexAdapter",
    "GrokAdapter",
    "GrokLiteLLMAdapter",
    "LiteLLMAdapter",
    # Functions
    "get_adapter",
    "register_adapter",
]
