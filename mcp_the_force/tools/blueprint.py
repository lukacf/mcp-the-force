"""Tool blueprint dataclass for dynamic tool generation."""

from dataclasses import dataclass
from typing import Type


@dataclass(frozen=True)
class ToolBlueprint:
    """Blueprint for generating tool classes dynamically."""

    model_name: str
    adapter_key: str  # "openai", "google", "xai"
    param_class: Type  # Route-based parameter class
    description: str
    timeout: int
    context_window: int
    tool_type: str = "chat"  # or "research"
    tool_name: str | None = None  # Optional friendly name for the tool
    cli: str | None = (
        None  # CLI name for CLI Agents feature (e.g., "claude", "codex", "gemini")
    )
