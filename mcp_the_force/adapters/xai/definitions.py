"""Single source of truth for xAI Grok adapter definitions.

This file contains all the model definitions, capabilities, parameters, and blueprint
generation logic for the xAI Grok adapter.
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


class GrokToolParams(BaseToolParams):
    """Grok-specific parameters with capability requirements."""

    # Live Search parameters
    search_mode: str = Route.adapter(
        default="auto",
        description="Live Search mode: 'auto', 'on', 'off'",
        requires_capability=lambda c: c.supports_live_search,
    )

    search_parameters: Optional[Dict[str, Any]] = Route.adapter(
        default=None,
        description="Live Search parameters (allowedWebsites, maxSearchResults, etc.)",
        requires_capability=lambda c: c.supports_live_search,
    )

    return_citations: bool = Route.adapter(
        default=True,
        description="Include citations from Live Search",
        requires_capability=lambda c: c.supports_live_search,
    )

    temperature: float = Route.adapter(
        default=0.7,
        description="Sampling temperature",
        requires_capability=lambda c: c.supports_temperature,
    )

    reasoning_effort: Optional[str] = Route.adapter(
        default=None,
        description="Reasoning effort for Grok mini models (low/high only)",
        requires_capability=lambda c: c.supports_reasoning_effort,
    )

    disable_memory_search: bool = Route.adapter(
        default=False,
        description="Disable search_project_history tool",
    )

    structured_output_schema: Optional[Dict[str, Any]] = Route.structured_output(
        description="JSON schema for structured output",
        requires_capability=lambda c: c.supports_structured_output,
    )


# ====================================================================
# CAPABILITY DEFINITIONS
# ====================================================================


@dataclass
class GrokBaseCapabilities(AdapterCapabilities):
    """Base capabilities shared by all Grok models."""

    provider: str = "xai"
    model_family: str = "grok"
    native_file_search: bool = False
    supports_tools: bool = True  # Changed from supports_functions
    supports_streaming: bool = True
    supports_live_search: bool = True
    supports_web_search: bool = False  # Grok uses Live Search, not web_search
    supports_vision: bool = False
    supports_temperature: bool = True
    supports_structured_output: bool = True
    supports_reasoning_effort: bool = False  # Default, overridden by mini models


@dataclass
class Grok3Capabilities(GrokBaseCapabilities):
    """Standard Grok 3 models with 131k context."""

    max_context_window: int = 131_000
    supports_reasoning_effort: bool = False
    description: str = "General purpose Grok 3 model"


@dataclass
class Grok3BetaCapabilities(Grok3Capabilities):
    """Grok 3 Beta model."""

    model_name: str = "grok-3-beta"
    description: str = "Deep reasoning using xAI Grok 3 Beta model (131k context)"


@dataclass
class Grok3FastCapabilities(Grok3Capabilities):
    """Grok 3 Fast model."""

    model_name: str = "grok-3-fast"
    description: str = "Fast inference with Grok 3"


@dataclass
class Grok4Capabilities(GrokBaseCapabilities):
    """Grok 4 models with 256k context."""

    model_name: str = "grok-4"
    max_context_window: int = 256_000
    supports_reasoning_effort: bool = False
    description: str = "Advanced assistant using xAI Grok 4 model (256k context, multi-agent reasoning)"


@dataclass
class Grok4HeavyCapabilities(Grok4Capabilities):
    """Grok 4 Heavy model."""

    model_name: str = "grok-4-heavy"
    description: str = "Maximum capability (if available)"


@dataclass
class GrokMiniCapabilities(GrokBaseCapabilities):
    """Grok mini models with reasoning effort support."""

    max_context_window: int = 32_000
    supports_reasoning_effort: bool = True
    description: str = "Quick responses with adjustable reasoning effort"


@dataclass
class GrokMiniBetaCapabilities(GrokMiniCapabilities):
    """Grok Mini Beta model."""

    model_name: str = "grok-3-mini-beta"
    description: str = "Beta version of mini model"


@dataclass
class GrokMiniFastCapabilities(GrokMiniCapabilities):
    """Grok Mini Fast model."""

    model_name: str = "grok-3-mini-fast"
    description: str = "Fast mini model"


# ====================================================================
# MODEL REGISTRY
# ====================================================================

GROK_MODEL_CAPABILITIES = {
    "grok-3-beta": Grok3BetaCapabilities(),
    "grok-3-fast": Grok3FastCapabilities(),
    "grok-4": Grok4Capabilities(),
    "grok-4-heavy": Grok4HeavyCapabilities(),
    "grok-3-mini": GrokMiniCapabilities(),
    "grok-3-mini-beta": GrokMiniBetaCapabilities(),
    "grok-3-mini-fast": GrokMiniFastCapabilities(),
}


# ====================================================================
# BLUEPRINT GENERATION
# ====================================================================

# Only generate tools for specific Grok models that are exposed to users
# We'll focus on the main models: grok-3-beta (reasoning) and grok-4 (advanced)
USER_FACING_MODELS = {
    "grok-3-beta": "Deep reasoning using xAI Grok 3 Beta model (131k context)",
    "grok-4": "Advanced assistant using xAI Grok 4 model (256k context, multi-agent reasoning)",
}


def _calculate_timeout(model_name: str) -> int:
    """Calculate appropriate timeout for a model."""
    if model_name == "grok-4":
        return 600  # 10 minutes for grok-4
    elif model_name == "grok-3-beta":
        return 420  # 7 minutes for grok-3-beta
    else:
        return 300  # Default 5 minutes


def _generate_and_register_blueprints():
    """Generate and register blueprints for user-facing Grok models."""
    blueprints = []

    for model_name, custom_description in USER_FACING_MODELS.items():
        capabilities = GROK_MODEL_CAPABILITIES[model_name]

        blueprint = ToolBlueprint(
            model_name=model_name,
            adapter_key="xai",
            param_class=GrokToolParams,
            description=custom_description,  # Use custom description for clarity
            timeout=_calculate_timeout(model_name),
            context_window=capabilities.max_context_window,
            tool_type="chat",  # All Grok models are chat tools
        )
        blueprints.append(blueprint)

    # Register all blueprints
    register_blueprints(blueprints)


# Auto-register blueprints when this module is imported
_generate_and_register_blueprints()
