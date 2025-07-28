"""Adapter module for AI model integrations.

This module contains protocol-based adapters for various AI providers.
The old BaseAdapter system has been replaced with a protocol-based architecture.

Adapters are registered in registry.py and accessed via get_adapter_class().
"""

# Re-export registry functions for convenience
from .registry import get_adapter_class, list_adapters
from .litellm_base import LiteLLMBaseAdapter

__all__ = [
    "get_adapter_class",
    "list_adapters",
    "LiteLLMBaseAdapter",
]
