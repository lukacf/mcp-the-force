"""Provider registry for vector stores."""

from typing import Dict, Callable, List
from .protocol import VectorStoreClient


# Global registry of vector store providers
_registry: Dict[str, Callable[[], VectorStoreClient]] = {}


def register(provider: str, factory: Callable[[], VectorStoreClient]) -> None:
    """Register a vector store provider.

    Args:
        provider: Provider name (e.g., "openai", "inmemory")
        factory: Factory function that creates a client instance
    """
    _registry[provider] = factory


def get_client(provider: str) -> VectorStoreClient:
    """Get a client for the specified provider.

    Args:
        provider: Provider name

    Returns:
        Client instance

    Raises:
        KeyError: If provider is not registered
    """
    if provider not in _registry:
        raise KeyError(f"Unknown vector store provider: {provider}")
    return _registry[provider]()


def list_providers() -> List[str]:
    """List all registered providers.

    Returns:
        List of provider names
    """
    return list(_registry.keys())
