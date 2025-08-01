"""Single source of truth for Google Gemini adapter definitions.

This file contains all the model definitions, capabilities, parameters, and blueprint
generation logic for the Google Gemini adapter.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from ..params import BaseToolParams
from ..capabilities import AdapterCapabilities
from ...tools.descriptors import Route
from ...tools.blueprint import ToolBlueprint
from ...tools.blueprint_registry import register_blueprints


# Max budget values from requirements
_MAX_BUDGET_PRO = 32768
_MAX_BUDGET_FLASH = 24576


# ====================================================================
# PARAMETER CLASS WITH CAPABILITY REQUIREMENTS
# ====================================================================


class GeminiToolParams(BaseToolParams):  # type: ignore[misc]
    """Gemini-specific parameters with capability requirements."""

    temperature: float = Route.adapter(  # type: ignore[assignment]
        default=1.0,
        description=(
            "(Optional) Controls the randomness of the model's output. Higher values result in more "
            "creative and varied responses, while lower values produce more deterministic output. "
            "Gemini models support a wider default temperature (1.0) compared to OpenAI models. "
            "Syntax: A float between 0.0 and 2.0. "
            "Default: 1.0. "
            "Example: temperature=0.5"
        ),
        requires_capability=lambda c: c.supports_temperature,
    )

    reasoning_effort: str = Route.adapter(  # type: ignore[assignment]
        default="medium",
        description=(
            "(Optional) Controls the 'thinking budget' allocated to the model for reasoning. Maps to "
            "a specific token budget for the model's internal reasoning process, affecting the depth "
            "of analysis. For Gemini 2.5 Pro: 'low'=13107 tokens, 'medium'=19660 tokens, 'high'=32768 tokens. "
            "For Gemini 2.5 Flash: 'low'=9830 tokens, 'medium'=14745 tokens, 'high'=24576 tokens. "
            "Syntax: A string, one of 'low', 'medium', or 'high'. "
            "Default: 'medium'. "
            "Example: reasoning_effort='high'"
        ),
        requires_capability=lambda c: c.supports_reasoning_effort,
    )

    disable_history_search: bool = Route.adapter(  # type: ignore[assignment]
        default=False,
        description=(
            "(Optional) If true, prevents the model from being able to use the search_project_history tool. "
            "Forces the model to rely only on the provided context and its own internal knowledge, "
            "without accessing the project's historical conversations and commits. "
            "Syntax: A boolean (true or false). "
            "Default: false. "
            "Example: disable_history_search=true"
        ),
    )

    structured_output_schema: Optional[Dict[str, Any]] = Route.structured_output(  # type: ignore[assignment, misc]
        description=(
            "(Optional) A JSON schema that the model's output must conform to. Forces the model to generate "
            "a response that is a valid JSON object matching the provided schema. Gemini models have more "
            "flexible schema validation compared to OpenAI models - 'required' and 'additionalProperties' "
            "are not mandatory. Supports complex nested schemas and various JSON Schema features. "
            "Syntax: A JSON object representing a valid JSON Schema. "
            "Example: {'type': 'object', 'properties': {'analysis': {'type': 'string'}, 'confidence': {'type': 'number'}}}"
        ),
        requires_capability=lambda c: c.supports_structured_output,
    )


# ====================================================================
# CAPABILITY DEFINITIONS
# ====================================================================


@dataclass
class GeminiBaseCapabilities(AdapterCapabilities):
    """Base capabilities shared by all Gemini models."""

    provider: str = "google"
    model_family: str = "gemini"
    supports_tools: bool = True  # Changed from supports_functions
    supports_streaming: bool = True
    supports_live_search: bool = False  # Gemini doesn't have Live Search like Grok
    supports_web_search: bool = False  # Gemini doesn't have web search
    supports_vision: bool = True  # Gemini is multimodal
    supports_reasoning_effort: bool = True  # Maps to thinking budget
    supports_temperature: bool = True
    supports_structured_output: bool = True

    # Reasoning effort mapping for thinking budget
    reasoning_effort_map: Dict[str, int] = field(default_factory=dict)


@dataclass
class Gemini25ProCapabilities(GeminiBaseCapabilities):
    """Gemini 2.5 Pro model capabilities."""

    model_name: str = "gemini-2.5-pro"
    max_context_window: int = 1_000_000
    description: str = "Deep multimodal analysis and complex reasoning"
    reasoning_effort_map: Dict[str, int] = field(
        default_factory=lambda: {
            "low": int(_MAX_BUDGET_PRO * 0.40),  # 13107
            "medium": int(_MAX_BUDGET_PRO * 0.60),  # 19660
            "high": _MAX_BUDGET_PRO,  # 32768
        }
    )


@dataclass
class Gemini25FlashCapabilities(GeminiBaseCapabilities):
    """Gemini 2.5 Flash model capabilities."""

    model_name: str = "gemini-2.5-flash"
    max_context_window: int = 1_000_000
    description: str = "Fast summarization and quick analysis"
    reasoning_effort_map: Dict[str, int] = field(
        default_factory=lambda: {
            "low": int(_MAX_BUDGET_FLASH * 0.40),  # 9830
            "medium": int(_MAX_BUDGET_FLASH * 0.60),  # 14745
            "high": _MAX_BUDGET_FLASH,  # 24576
        }
    )


# ====================================================================
# MODEL REGISTRY
# ====================================================================

GEMINI_MODEL_CAPABILITIES = {
    "gemini-2.5-pro": Gemini25ProCapabilities(),
    "gemini-2.5-flash": Gemini25FlashCapabilities(),
}


# ====================================================================
# BLUEPRINT GENERATION
# ====================================================================


def _calculate_timeout(model_name: str) -> int:
    """Calculate appropriate timeout for a model."""
    if "flash" in model_name:
        return 300  # 5 minutes for flash
    elif "pro" in model_name:
        return 480  # 8 minutes for pro
    else:
        return 300  # Default 5 minutes


def _get_friendly_name(model_name: str) -> str:
    """Generate a friendly tool name from the model name.

    Examples:
    - 'gemini-2.5-pro' -> 'chat_with_gemini25_pro'
    - 'gemini-2.5-flash' -> 'chat_with_gemini25_flash'
    """
    # Replace dots and hyphens with underscores
    clean_name = model_name.replace(".", "").replace("-", "_")
    return f"chat_with_{clean_name}"


def _generate_and_register_blueprints():
    """Generate and register blueprints for all Gemini models."""
    blueprints = []

    for model_name, capabilities in GEMINI_MODEL_CAPABILITIES.items():
        blueprint = ToolBlueprint(
            model_name=model_name,
            tool_name=_get_friendly_name(model_name),
            adapter_key="google",
            param_class=GeminiToolParams,
            description=capabilities.description,
            timeout=_calculate_timeout(model_name),
            context_window=capabilities.max_context_window,
            tool_type="chat",  # All Gemini models are chat tools
        )
        blueprints.append(blueprint)

    # Register all blueprints
    register_blueprints(blueprints)


# Auto-register blueprints when this module is imported
_generate_and_register_blueprints()
