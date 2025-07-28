"""Protocol-based Gemini adapter using LiteLLM."""

from .adapter import GeminiAdapter

# Import definitions to trigger blueprint registration
from . import definitions  # noqa: F401

# Re-export from definitions
from .definitions import GEMINI_MODEL_CAPABILITIES

__all__ = ["GeminiAdapter", "GEMINI_MODEL_CAPABILITIES"]
