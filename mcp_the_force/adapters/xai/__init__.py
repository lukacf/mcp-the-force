"""Protocol-based Grok adapter package.

This package implements the new protocol-based architecture for Grok models,
using LiteLLM internally and Pattern B (inheritance-only) for capabilities.
"""

from .adapter import GrokAdapter

# Import definitions to trigger blueprint registration
from . import definitions  # noqa: F401

# Re-export from definitions
from .definitions import (
    GROK_MODEL_CAPABILITIES,
    GrokBaseCapabilities,
    Grok3Capabilities,
    Grok41Capabilities,
    GrokMiniCapabilities,
)

__all__ = [
    "GrokAdapter",
    "GROK_MODEL_CAPABILITIES",
    "GrokBaseCapabilities",
    "Grok3Capabilities",
    "Grok41Capabilities",
    "GrokMiniCapabilities",
]
