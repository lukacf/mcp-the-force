"""Single source of truth for OpenAI adapter definitions.

This file contains all the model definitions, capabilities, parameters, and blueprint
generation logic for the OpenAI adapter.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass

from ..params import BaseToolParams
from ..capabilities import AdapterCapabilities
from ...tools.descriptors import Route
from ...tools.blueprint import ToolBlueprint
from ...tools.blueprint_registry import register_blueprints


# ====================================================================
# PARAMETER CLASS WITH CAPABILITY REQUIREMENTS
# ====================================================================


class OpenAIToolParams(BaseToolParams):  # type: ignore[misc]
    """OpenAI-specific parameters with capability requirements."""

    temperature: float = Route.adapter(  # type: ignore[assignment]
        default=0.2,
        description=(
            "(Optional) Controls the randomness of the model's output. Higher values result in more "
            "creative and varied responses, while lower values produce more deterministic and focused output. "
            "Only supported by GPT-4 models. O-series models (o3, o3-pro, o4-mini) do not support this parameter. "
            "Syntax: A float between 0.0 and 2.0. "
            "Default: 0.2. "
            "Example: temperature=0.8"
        ),
        requires_capability=lambda c: c.supports_temperature,
    )

    reasoning_effort: str = Route.adapter(  # type: ignore[assignment]
        default="medium",
        description=(
            "(Optional) Controls the amount of internal 'thinking' the model does before providing an answer. "
            "Higher effort results in more thorough and accurate reasoning but may increase latency. "
            "'low' is faster but may be less accurate for complex problems. "
            "Only supported by o-series models (o3, o3-pro, o4-mini). Not supported by GPT-4 models. "
            "Syntax: A string, one of 'low', 'medium', or 'high'. "
            "Default: 'medium' (or 'high' for o3-pro). "
            "Example: reasoning_effort='high'"
        ),
        requires_capability=lambda c: c.supports_reasoning_effort,
    )

    disable_history_search: bool = Route.adapter(  # type: ignore[assignment]
        default=False,
        description=(
            "(Optional) If true, prevents the model from being able to use the search_project_history tool "
            "in its response. Use this to force the model to rely only on the provided context and its own "
            "internal knowledge, preventing it from accessing potentially outdated historical information. "
            "Syntax: A boolean (true or false). "
            "Default: false. "
            "Example: disable_history_search=true"
        ),
    )

    structured_output_schema: Optional[Dict[str, Any]] = Route.structured_output(  # type: ignore[assignment, misc]
        description=(
            "(Optional) A JSON schema that the model's output must conform to. Forces the model to generate "
            "a response that is a valid JSON object matching the provided schema. For OpenAI models, the "
            "schema is strictly validated: all object properties must be listed in a 'required' array, and "
            "'additionalProperties' must be set to false. This ensures deterministic output structure. "
            "Syntax: A JSON object representing a valid JSON Schema. "
            "Example: {'type': 'object', 'properties': {'status': {'type': 'string'}, 'score': {'type': 'number'}}, "
            "'required': ['status', 'score'], 'additionalProperties': false}"
        ),
        requires_capability=lambda c: c.supports_structured_output,
    )


# ====================================================================
# CAPABILITY DEFINITIONS
# ====================================================================


@dataclass
class OpenAIBaseCapabilities(AdapterCapabilities):
    """Base capabilities for all OpenAI models."""

    provider: str = "openai"
    native_vector_store_provider: str = (
        "openai"  # OpenAI models require OpenAI vector stores
    )
    model_family: str = ""
    supports_tools: bool = True
    supports_web_search: bool = False
    supports_live_search: bool = False
    web_search_tool: str = ""
    supports_temperature: bool = True
    supports_reasoning_effort: bool = False
    supports_structured_output: bool = True
    supports_streaming: bool = True
    force_background: bool = False
    default_reasoning_effort: str = "medium"
    parallel_function_calls: int = 1  # Default to serial


@dataclass
class OSeriesCapabilities(OpenAIBaseCapabilities):
    """O-series specific capabilities."""

    model_family: str = "o-series"
    supports_reasoning_effort: bool = True
    supports_web_search: bool = True
    supports_live_search: bool = True
    web_search_tool: str = "web_search"
    supports_temperature: bool = False  # O-series doesn't support temperature!


@dataclass
class O3Capabilities(OSeriesCapabilities):
    """OpenAI o3 model capabilities."""

    model_name: str = "o3"
    max_context_window: int = 200_000
    description: str = "Chain-of-thought reasoning with web search (200k context)"
    parallel_function_calls: int = -1  # Unlimited


@dataclass
class CodexMiniCapabilities(OSeriesCapabilities):
    """OpenAI codex-mini model capabilities (o4-mini optimized for coding)."""

    model_name: str = "codex-mini-latest"
    max_context_window: int = 200_000
    description: str = "Fast coding-specialized reasoning model (200k context)"
    parallel_function_calls: int = -1  # Unlimited
    supports_web_search: bool = False  # Codex-mini doesn't support web search
    supports_live_search: bool = False  # Codex-mini doesn't support live search
    web_search_tool: str = ""  # No web search tool for codex-mini
    native_vector_store_provider: None = None  # type: ignore[assignment]  # Codex-mini doesn't support file search


@dataclass
class O3ProCapabilities(OSeriesCapabilities):
    """OpenAI o3-pro model capabilities."""

    model_name: str = "o3-pro"
    max_context_window: int = 200_000
    description: str = (
        "Deep analysis and formal reasoning with web search (200k context)"
    )
    force_background: bool = True  # Always use background mode
    supports_streaming: bool = False  # No streaming for o3-pro
    default_reasoning_effort: str = "high"
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

    model_name: str = "gpt-4.1"
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
    web_search_tool: str = (
        "web_search_preview"  # Deep research models require this tool
    )
    description: str = "Ultra-deep research with autonomous web search (30-60+ min)"


@dataclass
class O3DeepResearchCapabilities(DeepResearchCapabilities):
    """o3-deep-research model capabilities."""

    model_name: str = "o3-deep-research"
    max_context_window: int = 200_000
    description: str = (
        "Ultra-deep research with extensive web search (200k context, 10-60 min)"
    )


@dataclass
class O4MiniDeepResearchCapabilities(DeepResearchCapabilities):
    """o4-mini-deep-research model capabilities."""

    model_name: str = "o4-mini-deep-research"
    max_context_window: int = 200_000
    description: str = "Fast research with web search (200k context, 2-10 min)"


# ====================================================================
# MODEL REGISTRY
# ====================================================================

OPENAI_MODEL_CAPABILITIES = {
    "o3": O3Capabilities(),
    "o3-pro": O3ProCapabilities(),
    "codex-mini": CodexMiniCapabilities(),
    "gpt-4.1": GPT41Capabilities(),
    "o3-deep-research": O3DeepResearchCapabilities(),
    "o4-mini-deep-research": O4MiniDeepResearchCapabilities(),
}


# ====================================================================
# BLUEPRINT GENERATION
# ====================================================================


def _calculate_timeout(model_name: str) -> int:
    """Calculate appropriate timeout for a model."""
    if "deep-research" in model_name:
        return 3600  # 1 hour for deep research
    elif model_name == "o3-pro":
        return 2700  # 45 minutes for o3-pro
    elif model_name == "o3":
        return 1200  # 20 minutes for o3
    elif model_name == "gpt-4.1":
        return 300  # 5 minutes for gpt-4.1
    else:
        return 600  # 10 minutes default


def _generate_and_register_blueprints():
    """Generate and register blueprints for all OpenAI models."""
    blueprints = []

    for model_name, capabilities in OPENAI_MODEL_CAPABILITIES.items():
        # Determine tool type based on model name
        if "deep-research" in model_name:
            tool_type = "research"
        else:
            tool_type = "chat"

        # Use friendly name for codex-mini
        tool_name = None
        if model_name == "codex-mini":
            tool_name = "codex_mini"  # Keep the friendly name

        blueprint = ToolBlueprint(
            model_name=model_name,
            adapter_key="openai",
            param_class=OpenAIToolParams,
            description=capabilities.description,
            timeout=_calculate_timeout(model_name),
            context_window=capabilities.max_context_window,
            tool_type=tool_type,
            tool_name=tool_name,
        )
        blueprints.append(blueprint)

    # Register all blueprints
    register_blueprints(blueprints)


# Auto-register blueprints when this module is imported
_generate_and_register_blueprints()
