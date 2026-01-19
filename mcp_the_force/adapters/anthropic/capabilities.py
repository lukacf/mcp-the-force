"""Capability definitions for Anthropic Claude models."""

from dataclasses import dataclass
from typing import Dict

from ..capabilities import AdapterCapabilities


@dataclass
class AnthropicBaseCapabilities(AdapterCapabilities):
    """Base capabilities for all Anthropic models."""

    provider: str = "anthropic"
    model_family: str = "claude"
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_temperature: bool = True
    supports_structured_output: bool = True
    supports_vision: bool = True
    parallel_function_calls: int | None = (
        None  # Anthropic doesn't support parallel tool calls
    )


@dataclass
class Claude41OpusCapabilities(AnthropicBaseCapabilities):
    """Deprecated (superseded by Claude 4.5 Opus)."""


@dataclass
class Claude4SonnetCapabilities(AnthropicBaseCapabilities):
    """Capabilities for Claude 4 Sonnet."""

    model_name: str = "claude-sonnet-4-20250514"
    max_context_window: int = 1_000_000
    max_output_tokens: int = 64_000
    supports_reasoning_effort: bool = True
    description: str = "Balanced Claude for fast, high-quality writing and summaries with 1M context window. Speed: high. Tool use: reliable. When to use: Crisp docs, grounded Q&A, customer-facing replies, large document analysis—choose over Opus when latency matters."


@dataclass
class Claude45SonnetCapabilities(AnthropicBaseCapabilities):
    """Capabilities for Claude 4.5 Sonnet (1M context preview)."""

    model_name: str = "claude-sonnet-4-5"
    max_context_window: int = 1_000_000
    max_output_tokens: int = 64_000
    supports_reasoning_effort: bool = True
    description: str = "Claude 4.5 Sonnet with 1M context (beta). Faster, more factual, stronger coding/tool use than 4.1/4.0."


@dataclass
class Claude45OpusCapabilities(AnthropicBaseCapabilities):
    """Capabilities for Claude 4.5 Opus."""

    model_name: str = "claude-opus-4-5"
    max_context_window: int = 200_000  # 1M beta not announced for Opus 4.5
    max_output_tokens: int = 64_000
    supports_reasoning_effort: bool = True
    description: str = (
        "Claude 4.5 Opus: premium maximum-intelligence model with extended thinking."
    )


# Map of model names to their capability instances
ANTHROPIC_MODEL_CAPABILITIES: Dict[str, AnthropicBaseCapabilities] = {
    "claude-opus-4-5": Claude45OpusCapabilities(),
    "claude-sonnet-4-5": Claude45SonnetCapabilities(),
}
