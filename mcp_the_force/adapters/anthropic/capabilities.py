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
    """Capabilities for Claude 4.1 Opus."""

    model_name: str = "claude-opus-4-1-20250805"
    max_context_window: int = 200_000
    max_output_tokens: int = 32_000
    supports_reasoning_effort: bool = True
    description: str = "Anthropic's careful long-form reasoner/writer. Speed: low. Tool use: strong. When to use: Policy/legal/medical summaries, careful synthesis, premium writing where caution and clarity matter."


@dataclass
class Claude4SonnetCapabilities(AnthropicBaseCapabilities):
    """Capabilities for Claude 4 Sonnet."""

    model_name: str = "claude-sonnet-4-20250514"
    max_context_window: int = 1_000_000
    max_output_tokens: int = 64_000
    supports_reasoning_effort: bool = True
    description: str = "Balanced Claude for fast, high-quality writing and summaries with 1M context window. Speed: high. Tool use: reliable. When to use: Crisp docs, grounded Q&A, customer-facing replies, large document analysis—choose over Opus when latency matters."


@dataclass
class Claude3OpusCapabilities(AnthropicBaseCapabilities):
    """Capabilities for Claude 3 Opus."""

    model_name: str = "claude-3-opus-20240229"
    max_context_window: int = 200_000
    max_output_tokens: int = 8_000
    supports_reasoning_effort: bool = (
        False  # Claude 3 doesn't support extended thinking
    )
    description: str = "Prior flagship known for thoughtful, low-hallucination writing. Speed: low/medium. Tool use: good. When to use: Well-structured reports and literature summaries—prefer newer Sonnet/Opus 4-series or GPT-5.1 Codex for tool-heavy tasks."


# Map of model names to their capability instances
ANTHROPIC_MODEL_CAPABILITIES: Dict[str, AnthropicBaseCapabilities] = {
    "claude-opus-4-1-20250805": Claude41OpusCapabilities(),
    "claude-sonnet-4-20250514": Claude4SonnetCapabilities(),
    "claude-3-opus-20240229": Claude3OpusCapabilities(),
}
