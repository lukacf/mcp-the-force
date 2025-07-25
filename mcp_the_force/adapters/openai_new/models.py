"""OpenAI model capabilities using Pattern B (dataclass inheritance).

This module defines capabilities for all OpenAI models at compile time
using simple dataclass inheritance.
"""

from dataclasses import dataclass
from typing import Optional

from ..capabilities import AdapterCapabilities


@dataclass
class OpenAIBaseCapabilities(AdapterCapabilities):
    """Base capabilities shared by all OpenAI models."""

    native_file_search: bool = True
    supports_functions: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_live_search: bool = False
    supports_reasoning_effort: bool = False
    provider: str = "openai"
    model_family: str = "openai"

    # OpenAI-specific capabilities
    supports_structured_output: bool = True
    supports_previous_response_id: bool = True
    web_search_tool: str = "web_search"
    supports_custom_tools: bool = True  # Can use custom function tools
    supports_web_search: bool = False  # Base models don't support web search
    force_background: bool = False  # Most models can use either mode
    default_reasoning_effort: Optional[str] = None  # No default effort


@dataclass
class OSeriesCapabilities(OpenAIBaseCapabilities):
    """Capabilities for O-series reasoning models."""

    model_family: str = "o_series"
    supports_reasoning_effort: bool = True
    supports_live_search: bool = True  # via web_search tool
    supports_web_search: bool = True  # Override base to enable web search
    force_background: bool = False  # Can use streaming or background
    default_reasoning_effort: Optional[str] = None


@dataclass
class O3Capabilities(OSeriesCapabilities):
    """OpenAI o3 model capabilities."""

    max_context_window: int = 200_000
    description: str = "Chain-of-thought reasoning with web search (200k context)"
    parallel_function_calls: int = -1  # Unlimited


@dataclass
class O3ProCapabilities(OSeriesCapabilities):
    """OpenAI o3-pro model capabilities."""

    max_context_window: int = 200_000
    description: str = (
        "Deep analysis and formal reasoning with web search (200k context)"
    )
    force_background: bool = True  # Always use background mode
    supports_streaming: bool = False  # No streaming for o3-pro
    default_reasoning_effort: str = "high"
    parallel_function_calls: int = -1  # Unlimited


@dataclass
class O4MiniCapabilities(OSeriesCapabilities):
    """OpenAI o4-mini model capabilities."""

    max_context_window: int = 200_000
    description: str = "Fast reasoning model (200k context)"
    parallel_function_calls: int = -1  # Unlimited


@dataclass
class GPT4Capabilities(OpenAIBaseCapabilities):
    """GPT-4 series capabilities."""

    model_family: str = "gpt4"
    supports_live_search: bool = True  # via web_search tool
    supports_web_search: bool = True  # GPT-4 models support web search


@dataclass
class GPT41Capabilities(GPT4Capabilities):
    """GPT-4.1 model capabilities."""

    max_context_window: int = 1_000_000
    description: str = "Fast long-context processing with web search (1M context)"
    web_search_tool: str = "web_search"
    parallel_function_calls: int = -1  # Unlimited


@dataclass
class DeepResearchCapabilities(OSeriesCapabilities):
    """Deep research model capabilities."""

    model_family: str = "research"
    force_background: bool = True  # Always background
    supports_streaming: bool = False
    supports_live_search: bool = True
    description: str = "Ultra-deep research with autonomous web search (30-60+ min)"


@dataclass
class O3DeepResearchCapabilities(DeepResearchCapabilities):
    """o3-deep-research model capabilities."""

    max_context_window: int = 200_000
    description: str = (
        "Ultra-deep research with extensive web search (200k context, 10-60 min)"
    )


@dataclass
class O4MiniDeepResearchCapabilities(DeepResearchCapabilities):
    """o4-mini-deep-research model capabilities."""

    max_context_window: int = 200_000
    description: str = "Fast research with web search (200k context, 2-10 min)"


# Model registry
OPENAI_MODEL_CAPABILITIES = {
    "o3": O3Capabilities(),
    "o3-pro": O3ProCapabilities(),
    "o4-mini": O4MiniCapabilities(),
    "gpt-4.1": GPT41Capabilities(),
    "o3-deep-research": O3DeepResearchCapabilities(),
    "o4-mini-deep-research": O4MiniDeepResearchCapabilities(),
}
