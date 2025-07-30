"""Vector store abstraction for MCP The Force.

This package provides a unified interface for working with vector stores
across different providers (OpenAI, in-memory, etc.).
"""

from .protocol import VectorStore, VectorStoreClient, VSFile, SearchResult
from .errors import (
    VectorStoreError,
    QuotaExceededError,
    AuthError,
    UnsupportedFeatureError,
    TransientError,
)
from . import registry
from .manager import VectorStoreManager

# Import and register providers
from .in_memory import InMemoryClient
from .openai import OpenAIClient
from .hnsw import HnswVectorStoreClient
from ..config import get_settings

# Register providers
registry.register("inmemory", lambda: InMemoryClient())
registry.register("hnsw", lambda: HnswVectorStoreClient())


# Register OpenAI with API key from settings
def _create_openai_client():
    settings = get_settings()
    return OpenAIClient(api_key=settings.openai_api_key)


registry.register("openai", _create_openai_client)

__all__ = [
    # Protocols
    "VectorStore",
    "VectorStoreClient",
    "VSFile",
    "SearchResult",
    # Errors
    "VectorStoreError",
    "QuotaExceededError",
    "AuthError",
    "UnsupportedFeatureError",
    "TransientError",
    # Manager
    "VectorStoreManager",
    # Registry
    "registry",
    # Clients
    "InMemoryClient",
    "OpenAIClient",
    "HnswVectorStoreClient",
]
