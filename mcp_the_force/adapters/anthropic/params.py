"""Parameter definitions for Anthropic adapter tools."""

from typing import Optional, Dict, Any

from ..params import BaseToolParams
from ...tools.descriptors import Route


class AnthropicToolParams(BaseToolParams):  # type: ignore[misc]
    """Parameters for Anthropic Claude models."""

    # Standard parameters
    temperature: float = Route.adapter(  # type: ignore[assignment]
        default=0.7,
        description="Sampling temperature (0.0-1.0)",
        requires_capability=lambda c: c.supports_temperature,
    )

    # Anthropic requires max_tokens to be set
    max_tokens: int = Route.adapter(  # type: ignore[assignment]
        default=4096,
        description="Maximum tokens to generate (required by Anthropic, 1-64000)",
    )

    # Extended thinking support (similar to Gemini)
    reasoning_effort: str = Route.adapter(  # type: ignore[assignment]
        default="medium",
        description="Extended thinking effort level (low/medium/high)",
        requires_capability=lambda c: c.supports_reasoning_effort,
    )

    # Direct thinking budget control (for advanced users)
    thinking_budget: Optional[int] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description="Explicit thinking token budget (1024-32768, overrides reasoning_effort)",
        requires_capability=lambda c: c.supports_reasoning_effort,
    )

    # Structured output support
    structured_output_schema: Optional[Dict[str, Any]] = Route.structured_output(  # type: ignore[assignment, misc]
        requires_capability=lambda c: c.supports_structured_output
    )

    # History control
    disable_history_search: bool = Route.adapter(  # type: ignore[assignment]
        default=False,
        description="Disable access to project history search",
    )

    # Session management
    disable_history_record: bool = Route.adapter(  # type: ignore[assignment]
        default=False,
        description="Prevent storing this conversation in project history",
    )

    def get_thinking_budget(self) -> Optional[int]:
        """Get the thinking budget based on effort level or explicit value."""
        if self.thinking_budget is not None:
            return self.thinking_budget

        # Map reasoning effort to thinking budget (similar to Gemini)
        effort_to_budget = {
            "low": 4096,
            "medium": 8192,
            "high": 16384,
        }
        return effort_to_budget.get(self.reasoning_effort, 8192)
