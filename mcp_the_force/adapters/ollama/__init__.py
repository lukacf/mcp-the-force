"""Ollama adapter for MCP The-Force."""

from .adapter import OllamaAdapter
from .blueprint_generator import OllamaBlueprints

# Singleton instance for blueprint management
blueprint_generator = OllamaBlueprints()

__all__ = ["OllamaAdapter", "blueprint_generator"]
