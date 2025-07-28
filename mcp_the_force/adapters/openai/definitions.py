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


class OpenAIToolParams(BaseToolParams):
    """OpenAI-specific parameters with capability requirements."""

    temperature: float = Route.adapter(
        default=0.2,
        description="Model temperature for response creativity",
        requires_capability=lambda c: c.supports_temperature,
    )

    reasoning_effort: str = Route.adapter(
        default="medium",
        description="Reasoning effort level (low/medium/high)",
        requires_capability=lambda c: c.supports_reasoning_effort,
    )

    disable_memory_search: bool = Route.adapter(
        default=False,
        description="Disable automatic memory search",
    )

    structured_output_schema: Optional[Dict[str, Any]] = Route.structured_output(
        description="JSON schema for structured output",
        requires_capability=lambda c: c.supports_structured_output,
    )


# ====================================================================
# CAPABILITY DEFINITIONS
# ====================================================================


@dataclass
class OpenAIBaseCapabilities(AdapterCapabilities):
    """Base capabilities for all OpenAI models."""

    provider: str = "openai"
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
class O4MiniCapabilities(OSeriesCapabilities):
    """OpenAI o4-mini model capabilities."""

    model_name: str = "o4-mini"
    max_context_window: int = 200_000
    description: str = "Fast reasoning model (200k context)"
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
    "o4-mini": O4MiniCapabilities(),
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

        blueprint = ToolBlueprint(
            model_name=model_name,
            adapter_key="openai",
            param_class=OpenAIToolParams,
            description=capabilities.description,
            timeout=_calculate_timeout(model_name),
            context_window=capabilities.max_context_window,
            tool_type=tool_type,
        )
        blueprints.append(blueprint)

    # Register all blueprints
    register_blueprints(blueprints)


# Auto-register blueprints when this module is imported
_generate_and_register_blueprints()
