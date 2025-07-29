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
    native_file_search: bool = False
    supports_vision: bool = True
    parallel_function_calls: int | None = (
        None  # Anthropic doesn't support parallel tool calls
    )


@dataclass
class Claude4OpusCapabilities(AnthropicBaseCapabilities):
    """Capabilities for Claude 4 Opus."""

    model_name: str = "claude-4-opus"
    max_context_window: int = 200_000
    max_output_tokens: int = 32_000
    supports_reasoning_effort: bool = True
    description: str = "Deep analysis and formal reasoning with extended thinking (200k context, 32k output)"


@dataclass
class Claude4SonnetCapabilities(AnthropicBaseCapabilities):
    """Capabilities for Claude 4 Sonnet."""

    model_name: str = "claude-4-sonnet"
    max_context_window: int = 200_000
    max_output_tokens: int = 64_000
    supports_reasoning_effort: bool = True
    description: str = (
        "Fast long-context processing with extended thinking (200k context, 64k output)"
    )


@dataclass
class Claude3OpusCapabilities(AnthropicBaseCapabilities):
    """Capabilities for Claude 3 Opus."""

    model_name: str = "claude-3-opus"
    max_context_window: int = 200_000
    max_output_tokens: int = 8_000
    supports_reasoning_effort: bool = (
        False  # Claude 3 doesn't support extended thinking
    )
    description: str = "Exceptional theory of mind and deep, thoughtful discussions (200k context, 8k output)"


# Map of model names to their capability instances
ANTHROPIC_MODEL_CAPABILITIES: Dict[str, AnthropicBaseCapabilities] = {
    "claude-4-opus": Claude4OpusCapabilities(),
    "claude-4-sonnet": Claude4SonnetCapabilities(),
    "claude-3-opus": Claude3OpusCapabilities(),
}
