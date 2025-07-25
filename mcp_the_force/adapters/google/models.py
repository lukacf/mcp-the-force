"""Model definitions for Gemini adapter using Pattern B."""

from dataclasses import dataclass, field
from typing import Dict, Optional
from ..capabilities import AdapterCapabilities

# Max budget values from requirements
_MAX_BUDGET_PRO = 32768
_MAX_BUDGET_FLASH = 24576


@dataclass
class GeminiBaseCapabilities(AdapterCapabilities):
    """Base capabilities shared by all Gemini models."""

    native_file_search: bool = False
    supports_functions: bool = True
    supports_streaming: bool = True
    supports_live_search: bool = False  # Gemini doesn't have Live Search like Grok
    supports_vision: bool = True  # Gemini is multimodal
    supports_reasoning_effort: bool = True  # Maps to thinking budget
    provider: str = "google"
    model_family: str = "gemini"


@dataclass
class Gemini25ProCapabilities(GeminiBaseCapabilities):
    """Gemini 2.5 Pro model capabilities."""

    max_context_window: int = 1_000_000
    description: str = "Deep multimodal analysis and complex reasoning"
    reasoning_effort_map: Dict[str, int] = field(
        default_factory=lambda: {
            "low": int(_MAX_BUDGET_PRO * 0.40),  # 13107
            "medium": int(_MAX_BUDGET_PRO * 0.60),  # 19660
            "high": _MAX_BUDGET_PRO,  # 32768
        }
    )


@dataclass
class Gemini25FlashCapabilities(GeminiBaseCapabilities):
    """Gemini 2.5 Flash model capabilities."""

    max_context_window: int = 1_000_000
    description: str = "Fast summarization and quick analysis"
    reasoning_effort_map: Dict[str, int] = field(
        default_factory=lambda: {
            "low": int(_MAX_BUDGET_FLASH * 0.40),  # 9830
            "medium": int(_MAX_BUDGET_FLASH * 0.60),  # 14745
            "high": _MAX_BUDGET_FLASH,  # 24576
        }
    )


# Model capabilities registry
GEMINI_MODEL_CAPABILITIES: Dict[str, AdapterCapabilities] = {
    "gemini-2.5-pro": Gemini25ProCapabilities(),
    "gemini-2.5-flash": Gemini25FlashCapabilities(),
}


def get_model_capabilities(model_name: str) -> Optional[AdapterCapabilities]:
    """Get capabilities for a specific model."""
    return GEMINI_MODEL_CAPABILITIES.get(model_name)
