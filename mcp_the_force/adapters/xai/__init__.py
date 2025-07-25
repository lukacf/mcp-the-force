"""Protocol-based Grok adapter package.

This package implements the new protocol-based architecture for Grok models,
using LiteLLM internally and Pattern B (inheritance-only) for capabilities.
"""

from .adapter import GrokAdapter
from .models import (
    GROK_MODEL_CAPABILITIES,
    GrokBaseCapabilities,
    Grok3Capabilities,
    Grok4Capabilities,
    GrokMiniCapabilities,
)

__all__ = [
    "GrokAdapter",
    "GROK_MODEL_CAPABILITIES",
    "GrokBaseCapabilities",
    "Grok3Capabilities",
    "Grok4Capabilities",
    "GrokMiniCapabilities",
]
