"""Anthropic adapter definitions for compatibility with tool factories.

This module re-exports the model capabilities to maintain consistency
with other adapters that expect a definitions.py module.
"""

# Re-export capabilities for factory compatibility
from .capabilities import (
    ANTHROPIC_MODEL_CAPABILITIES,
    AnthropicBaseCapabilities,
    Claude3OpusCapabilities,
    Claude41OpusCapabilities,
    Claude4SonnetCapabilities,
)

# Re-export params for consistency
from .params import AnthropicToolParams

__all__ = [
    "ANTHROPIC_MODEL_CAPABILITIES",
    "AnthropicBaseCapabilities",
    "Claude3OpusCapabilities",
    "Claude41OpusCapabilities",
    "Claude4SonnetCapabilities",
    "AnthropicToolParams",
]
