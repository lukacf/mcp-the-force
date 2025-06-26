"""OpenAI adapter package.

This package provides an adapter for OpenAI models using the Responses API.
"""

from .adapter import OpenAIAdapter
from .errors import AdapterException, ErrorCategory

__all__ = ["OpenAIAdapter", "AdapterException", "ErrorCategory"]
