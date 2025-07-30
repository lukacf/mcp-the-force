"""Adapter capabilities declaration."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AdapterCapabilities:
    """What the framework needs to know about an adapter.

    This is used by the executor and tool handler to make decisions
    about how to interact with the adapter.
    """

    # Core capabilities
    native_vector_store_provider: Optional[str] = (
        None  # Provider required for native file search
    )
    supports_functions: bool = True  # Legacy name for supports_tools
    supports_tools: bool = True  # Tools/function calling
    supports_streaming: bool = True
    supports_temperature: bool = True  # Temperature parameter
    supports_structured_output: bool = True  # JSON schema output
    supports_web_search: bool = False  # Web search capability
    parallel_function_calls: Optional[int] = None
    max_context_window: Optional[int] = None

    # Provider-specific capabilities
    supports_live_search: bool = False  # Grok Live Search
    supports_reasoning_effort: bool = False  # OpenAI/Grok mini models
    supports_vision: bool = False  # Multimodal support

    # Additional metadata
    description: str = ""
    provider: str = ""
    model_family: str = ""
    model_name: str = ""  # Specific model name
