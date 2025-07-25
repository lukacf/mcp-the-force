"""Type-safe parameter definitions for adapters.

These parameter classes are used by the protocol-based adapters to define
their expected parameters. They work alongside the Route descriptors used
in ToolSpec classes.
"""

from typing import List, Optional, Any, Dict
from ..tools.descriptors import Route


class BaseToolParams:
    """Parameters every tool has.

    This is not a dataclass - it works with Route descriptors like ToolSpec.
    The protocol-based adapters will receive instances with these attributes
    populated from the Route descriptors.
    """

    instructions: str = Route.prompt(pos=0, description="User instructions")
    output_format: str = Route.prompt(pos=1, description="Expected output format")
    context: List[str] = Route.prompt(pos=2, description="Context files/directories")
    session_id: str = Route.session(description="Session ID for conversation")


class GrokToolParams(BaseToolParams):
    """Grok-specific parameters.

    Extends BaseToolParams with Grok-specific Route descriptors.
    """

    # Optional parameters with defaults
    search_mode: str = Route.adapter(
        default="auto", description="Live Search mode: 'auto', 'on', 'off'"
    )
    search_parameters: Optional[Dict[str, Any]] = Route.adapter(
        default=None,
        description="Live Search parameters (allowedWebsites, maxSearchResults, etc.)",
    )
    return_citations: bool = Route.adapter(
        default=True, description="Include citations from Live Search"
    )
    temperature: float = Route.adapter(default=0.7, description="Sampling temperature")
    reasoning_effort: Optional[str] = Route.adapter(
        default=None,
        description="Reasoning effort for Grok mini models (low/high only, not supported by Grok 4)",
    )
    disable_memory_search: bool = Route.adapter(
        default=False, description="Disable search_project_history tool"
    )
    structured_output_schema: Optional[Dict[str, Any]] = Route.adapter(
        default=None, description="JSON schema for structured output"
    )


class OpenAIToolParams(BaseToolParams):
    """OpenAI-specific parameters."""

    temperature: float = Route.adapter(default=0.2)
    reasoning_effort: str = Route.adapter(
        default="medium", description="Reasoning effort (low/medium/high)"
    )
    disable_memory_search: bool = Route.adapter(default=False)
    structured_output_schema: Optional[Dict[str, Any]] = Route.adapter(default=None)


class GeminiToolParams(BaseToolParams):
    """Gemini-specific parameters."""

    temperature: float = Route.adapter(default=1.0)
    reasoning_effort: str = Route.adapter(default="medium")
    disable_memory_search: bool = Route.adapter(default=False)
    structured_output_schema: Optional[Dict[str, Any]] = Route.adapter(default=None)


class LiteLLMParams(BaseToolParams):
    """Universal LiteLLM parameters with passthrough."""

    temperature: float = Route.adapter(default=0.7)
    extras: Dict[str, Any] = Route.adapter(
        default_factory=dict, description="Provider-specific parameters to pass through"
    )
