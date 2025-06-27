"""Model definitions for Vertex AI adapter."""

from typing import Dict

# Context window limits for Gemini models (in tokens)
model_context_windows: Dict[str, int] = {
    "gemini-2.5-pro": 1_000_000,  # 1M tokens
    "gemini-2.5-flash": 1_000_000,  # 1M tokens
}


def get_context_window(model: str) -> int:
    """Get context window for a model, with fallback."""
    return model_context_windows.get(model, 32_000)  # Conservative fallback
