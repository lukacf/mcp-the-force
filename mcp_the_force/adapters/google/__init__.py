"""Protocol-based Gemini adapter using LiteLLM."""

from .adapter import GeminiAdapter
from .models import GEMINI_MODEL_CAPABILITIES

__all__ = ["GeminiAdapter", "GEMINI_MODEL_CAPABILITIES"]
