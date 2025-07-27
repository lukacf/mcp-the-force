"""OpenAI adapter package - Protocol-based implementation.

This package provides a protocol-based adapter for OpenAI models using the native OpenAI SDK.
Unlike other adapters that use LiteLLM for translation, this adapter uses the OpenAI SDK
directly since LiteLLM's purpose is to translate TO OpenAI format.
"""

from .adapter import OpenAIProtocolAdapter
from .errors import AdapterException, ErrorCategory
# from . import cancel_aware_flow  # Apply cancellation patch  # noqa: F401  # No longer needed with mcp@d4e14a4

# Import definitions to trigger blueprint registration
from . import definitions  # noqa: F401

# Re-export from definitions
from .definitions import OPENAI_MODEL_CAPABILITIES

__all__ = [
    "OpenAIProtocolAdapter",
    "OPENAI_MODEL_CAPABILITIES",
    "AdapterException",
    "ErrorCategory",
]
