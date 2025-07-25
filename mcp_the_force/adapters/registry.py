"""Simple adapter registry for dynamic adapter loading."""

import importlib
from typing import Type, Dict, Tuple, Any

_ADAPTER_REGISTRY: Dict[str, Tuple[str, str]] = {
    "openai": ("mcp_the_force.adapters.openai.adapter", "OpenAIProtocolAdapter"),
    "google": ("mcp_the_force.adapters.google.adapter", "GeminiAdapter"),
    "xai": ("mcp_the_force.adapters.xai.adapter", "GrokAdapter"),
}


def get_adapter_class(key: str) -> Type[Any]:
    """Dynamically import and return adapter class."""
    if key not in _ADAPTER_REGISTRY:
        raise KeyError(f"Unknown adapter: {key}")

    module_path, class_name = _ADAPTER_REGISTRY[key]
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def list_adapters() -> list[str]:
    """List all registered adapter keys."""
    return list(_ADAPTER_REGISTRY.keys())
