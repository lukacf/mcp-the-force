"""OpenAI adapter package.

This package provides an adapter for OpenAI models using the Responses API.
"""

from .adapter import OpenAIAdapter
from .errors import AdapterException, ErrorCategory
from . import cancel_aware_flow  # Apply cancellation patch  # noqa: F401

__all__ = ["OpenAIAdapter", "AdapterException", "ErrorCategory"]
