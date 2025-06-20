"""Adapter module for AI model integrations."""
from typing import Dict, Tuple, Type, Optional
from .base import BaseAdapter
from .openai_adapter import OpenAIAdapter
from .vertex_adapter import VertexAdapter
import logging

logger = logging.getLogger(__name__)

# Adapter registry
ADAPTER_REGISTRY: Dict[str, Type[BaseAdapter]] = {
    "openai": OpenAIAdapter,
    "vertex": VertexAdapter,
}

# Adapter instance cache
_ADAPTER_CACHE: Dict[Tuple[str, str], BaseAdapter] = {}

def get_adapter(adapter_key: str, model_name: str) -> Tuple[Optional[BaseAdapter], Optional[str]]:
    """Get or create an adapter instance.
    
    Args:
        adapter_key: Key identifying the adapter type (e.g., "openai", "vertex")
        model_name: Name of the model (e.g., "o3", "gemini-2.5-pro")
        
    Returns:
        Tuple of (adapter instance, error message)
    """
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
        adapter = adapter_class(model_name)
        _ADAPTER_CACHE[cache_key] = adapter
        logger.info(f"Created {adapter_key} adapter for {model_name}")
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
    logger.info(f"Registered adapter: {key}")

__all__ = ["BaseAdapter", "OpenAIAdapter", "VertexAdapter", "get_adapter", "register_adapter"]
