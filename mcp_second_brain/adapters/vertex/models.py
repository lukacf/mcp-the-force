"""Model definitions for Vertex AI adapter."""

from pydantic import BaseModel
from typing import Dict

# --- Model Capabilities ---


class ModelCapability(BaseModel):
    """Defines the schema for a single Vertex model's capabilities."""

    context_window: int
    max_thinking_budget: int
    supports_thinking_budget: bool = True
    reasoning_effort_map: Dict[str, int]


# Max budget values from requirements
_MAX_BUDGET_PRO = 32768
_MAX_BUDGET_FLASH = 24576

# Model capabilities registry
model_capabilities: Dict[str, ModelCapability] = {
    "gemini-2.5-pro": ModelCapability(
        context_window=2_000_000,  # Consistent with adapter.py
        max_thinking_budget=_MAX_BUDGET_PRO,
        reasoning_effort_map={
            "low": int(_MAX_BUDGET_PRO * 0.40),  # 13107
            "medium": int(_MAX_BUDGET_PRO * 0.60),  # 19660
            "high": _MAX_BUDGET_PRO,  # 32768
        },
    ),
    "gemini-2.5-flash": ModelCapability(
        context_window=2_000_000,  # Consistent with adapter.py
        max_thinking_budget=_MAX_BUDGET_FLASH,
        reasoning_effort_map={
            "low": int(_MAX_BUDGET_FLASH * 0.40),  # 9830
            "medium": int(_MAX_BUDGET_FLASH * 0.60),  # 14745
            "high": _MAX_BUDGET_FLASH,  # 24576
        },
    ),
}

# --- Helper Functions ---


def get_context_window(model: str) -> int:
    """Get context window for a model, with fallback."""
    capability = model_capabilities.get(model)
    if capability:
        return capability.context_window
    return 32_000  # Conservative fallback
