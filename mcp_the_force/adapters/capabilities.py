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
    native_file_search: bool = False
    supports_functions: bool = True
    supports_streaming: bool = True
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
