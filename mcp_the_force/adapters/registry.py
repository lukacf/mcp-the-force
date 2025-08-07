"""Simple adapter registry for dynamic adapter loading."""

import importlib
from typing import Type, Dict, Tuple, Any

_ADAPTER_REGISTRY: Dict[str, Tuple[str, str]] = {
    "openai": ("mcp_the_force.adapters.openai.adapter", "OpenAIProtocolAdapter"),
    "google": ("mcp_the_force.adapters.google.adapter", "GeminiAdapter"),
    "xai": ("mcp_the_force.adapters.xai.adapter", "GrokAdapter"),
    "anthropic": ("mcp_the_force.adapters.anthropic.adapter", "AnthropicAdapter"),
    "ollama": ("mcp_the_force.adapters.ollama.adapter", "OllamaAdapter"),
}


def get_adapter_class(key: str) -> Type[Any]:
    """Dynamically import and return adapter class."""
    # Check if we should use mock adapter for testing
    from ..config import get_settings

    settings = get_settings()
    if settings.adapter_mock:
        from .mock_adapter import MockAdapter

        return MockAdapter

    if key not in _ADAPTER_REGISTRY:
        raise KeyError(f"Unknown adapter: {key}")

    module_path, class_name = _ADAPTER_REGISTRY[key]
    module = importlib.import_module(module_path)
    return getattr(module, class_name)  # type: ignore[no-any-return]


def list_adapters() -> list[str]:
    """List all registered adapter keys."""
    return list(_ADAPTER_REGISTRY.keys())
