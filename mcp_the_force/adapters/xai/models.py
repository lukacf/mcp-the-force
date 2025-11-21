"""Grok model capabilities using Pattern B (inheritance-only).

This module defines all Grok model capabilities using dataclass inheritance
for type safety and zero runtime logic. Each model's capabilities are defined
at compile time through inheritance.
"""

from dataclasses import dataclass
from ..capabilities import AdapterCapabilities


@dataclass
class GrokBaseCapabilities(AdapterCapabilities):
    """Base capabilities shared by all Grok models."""

    supports_functions: bool = True
    supports_streaming: bool = True
    supports_live_search: bool = True
    supports_vision: bool = False
    provider: str = "xai"
    model_family: str = "grok"


@dataclass
class Grok3Capabilities(GrokBaseCapabilities):
    """Standard Grok 3 models with 131k context."""

    max_context_window: int = 131_000
    supports_reasoning_effort: bool = False
    description: str = "General purpose Grok 3 model"


@dataclass
class Grok3BetaCapabilities(Grok3Capabilities):
    """Grok 3 Beta model."""

    pass  # Uses all defaults from Grok3Capabilities


@dataclass
class Grok3FastCapabilities(Grok3Capabilities):
    """Grok 3 Fast model."""

    description: str = "Fast inference with Grok 3"


@dataclass
class Grok41Capabilities(GrokBaseCapabilities):
    """Grok 4.1 models with 256k context."""

    max_context_window: int = 256_000
    supports_reasoning_effort: bool = False
    description: str = "Grok 4.1: Enhanced reasoning, reduced hallucinations, 256k context. Advanced xAI model with multi-agent reasoning and long context."


@dataclass
class Grok4HeavyCapabilities(Grok41Capabilities):
    """Grok 4 Heavy model."""

    description: str = "Maximum capability (if available)"


@dataclass
class GrokMiniCapabilities(GrokBaseCapabilities):
    """Grok mini models with reasoning effort support."""

    max_context_window: int = 32_000
    supports_reasoning_effort: bool = True
    description: str = "Quick responses with adjustable reasoning effort"


@dataclass
class GrokMiniBetaCapabilities(GrokMiniCapabilities):
    """Grok Mini Beta model."""

    description: str = "Beta version of mini model"


@dataclass
class GrokMiniFastCapabilities(GrokMiniCapabilities):
    """Grok Mini Fast model."""

    description: str = "Fast mini model"


# Model registry - simple mapping of names to instances
GROK_MODEL_CAPABILITIES = {
    "grok-3-beta": Grok3BetaCapabilities(),
    "grok-3-fast": Grok3FastCapabilities(),
    "grok-4.1": Grok41Capabilities(),
    "grok-4-heavy": Grok4HeavyCapabilities(),
    "grok-3-mini": GrokMiniCapabilities(),
    "grok-3-mini-beta": GrokMiniBetaCapabilities(),
    "grok-3-mini-fast": GrokMiniFastCapabilities(),
}
