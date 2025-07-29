"""Anthropic adapter for MCP The-Force server."""

from .adapter import AnthropicAdapter

# Import blueprints to trigger registration
from . import blueprints  # noqa: F401

# Re-export from capabilities
from .capabilities import ANTHROPIC_MODEL_CAPABILITIES

__all__ = ["AnthropicAdapter", "ANTHROPIC_MODEL_CAPABILITIES"]
