"""OpenAI model capabilities using Pattern B (dataclass inheritance).

This module defines capabilities for all OpenAI models at compile time
using simple dataclass inheritance.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

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
    supports_temperature: bool = True  # Most models support temperature

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
    supports_temperature: bool = False  # O-series doesn't support temperature


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
class CodexMiniCapabilities(OSeriesCapabilities):
    """OpenAI codex-mini model capabilities (o4-mini optimized for coding)."""

    max_context_window: int = 200_000
    description: str = "Fast coding-specialized reasoning model (200k context)"
    parallel_function_calls: int = -1  # Unlimited
    supports_web_search: bool = False  # Codex-mini doesn't support web search
    supports_live_search: bool = False  # Codex-mini doesn't support live search
    web_search_tool: str = ""  # No web search tool for codex-mini


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
    "codex-mini": CodexMiniCapabilities(),
    "gpt-4.1": GPT41Capabilities(),
    "o3-deep-research": O3DeepResearchCapabilities(),
    "o4-mini-deep-research": O4MiniDeepResearchCapabilities(),
}

# Export capabilities for other modules
__all__ = ["OpenAIRequest", "OPENAI_MODEL_CAPABILITIES"]


class OpenAIRequest(BaseModel):
    """Validated request parameters for OpenAI Responses API."""

    model: str
    input: Union[str, List[Dict[str, Any]]]
    instructions: Optional[str] = None
    previous_response_id: Optional[str] = None
    stream: bool = False
    background: bool = False
    # This field is now internal and will be transformed into the 'reasoning' dict.
    reasoning_effort: Optional[str] = Field(default=None, exclude=True)
    temperature: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    parallel_tool_calls: bool = Field(default=True, alias="parallel_tool_calls")

    # Internal fields not sent to OpenAI API
    vector_store_ids: Optional[List[str]] = Field(default=None, exclude=True)
    structured_output_schema: Optional[Dict[str, Any]] = Field(
        default=None, exclude=True
    )
    disable_memory_search: bool = Field(default=False, exclude=True)
    return_debug: bool = Field(default=False, exclude=True)
    max_output_tokens: Optional[int] = Field(default=None, exclude=True)
    timeout: float = Field(default=300.0, exclude=True)

    def to_api_format(self) -> Dict[str, Any]:
        """Convert to OpenAI API format, handling nested reasoning and structured outputs."""
        # The `reasoning_effort` field is now excluded by `exclude=True` in its definition
        api_data = self.model_dump(by_alias=True, exclude_none=True)

        # Manually construct the 'reasoning' parameter if effort is specified.
        if self.reasoning_effort:
            # Check if the model actually supports it to avoid sending invalid params.
            capability = OPENAI_MODEL_CAPABILITIES.get(self.model)
            if capability and capability.supports_reasoning_effort:
                api_data["reasoning"] = {"effort": self.reasoning_effort}

        # Include structured output schema if provided
        # The actual schema transformation will be done in flow.py
        if self.structured_output_schema:
            api_data["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "structured_output",
                    "schema": self.structured_output_schema,
                }
            }

        return api_data  # type: ignore[no-any-return]
