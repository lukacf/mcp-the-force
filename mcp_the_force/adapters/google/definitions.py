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
from ...utils.capability_formatter import format_capabilities


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
            "of analysis. For Gemini 3 Pro Preview: 'low'=13107 tokens, 'medium'=19660 tokens, 'high'=32768 tokens. "
            "For Gemini 3 Flash Preview: 'low'=9830 tokens, 'medium'=14745 tokens, 'high'=24576 tokens. "
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
class Gemini3ProPreviewCapabilities(GeminiBaseCapabilities):
    """Gemini 3 Pro Preview model capabilities."""

    model_name: str = "gemini-3-pro-preview"
    max_context_window: int = 1_000_000
    description: str = "Next-gen multimodal analyst (preview) with 1M input context and strong tools. Use for giant code/document synthesis and design reviews where breadth matters."
    reasoning_effort_map: Dict[str, int] = field(
        default_factory=lambda: {
            "low": int(_MAX_BUDGET_PRO * 0.40),  # reuse existing budget mapping
            "medium": int(_MAX_BUDGET_PRO * 0.60),
            "high": _MAX_BUDGET_PRO,
        }
    )


@dataclass
class Gemini3FlashPreviewCapabilities(GeminiBaseCapabilities):
    """Gemini 3 Flash Preview model capabilities.

    Added: December 2025 (replaced gemini-2.5-flash)
    Google's fast frontier-class model with upgraded visual/spatial reasoning.
    """

    model_name: str = "gemini-3-flash-preview"
    max_context_window: int = 1_000_000
    description: str = "Fast frontier-class model with upgraded visual/spatial reasoning and agentic coding. Speed: very high. When to use: Rapid summaries, extraction, first-pass analysis—escalate to Pro for complex reasoning."
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
    "gemini-3-pro-preview": Gemini3ProPreviewCapabilities(),
    "gemini-3-flash-preview": Gemini3FlashPreviewCapabilities(),
}


# ====================================================================
# BLUEPRINT GENERATION
# ====================================================================


def _calculate_timeout(model_name: str) -> int:
    """Calculate appropriate timeout for a model."""
    if "flash" in model_name:
        return 600  # 10 minutes for flash
    elif "pro" in model_name:
        return 1800  # 30 minutes for pro (needed for large context + tool use)
    else:
        return 600  # Default 10 minutes


def _get_friendly_name(model_name: str) -> str:
    """Generate a friendly tool name from the model name.

    Examples:
    - 'gemini-3-pro-preview' -> 'chat_with_gemini3_pro_preview'
    - 'gemini-3-flash-preview' -> 'chat_with_gemini3_flash_preview'
    """
    # Replace dots and hyphens with underscores
    clean_name = model_name.replace(".", "").replace("-", "_")
    return f"chat_with_{clean_name}"


def _generate_and_register_blueprints():
    """Generate and register blueprints for all Gemini models."""
    blueprints = []

    for model_name, capabilities in GEMINI_MODEL_CAPABILITIES.items():
        # Format capabilities and append to description
        capability_info = format_capabilities(capabilities)
        full_description = capabilities.description
        if capability_info:
            full_description = f"{capabilities.description} [{capability_info}]"

        blueprint = ToolBlueprint(
            model_name=model_name,
            tool_name=_get_friendly_name(model_name),
            adapter_key="google",
            param_class=GeminiToolParams,
            description=full_description,
            timeout=_calculate_timeout(model_name),
            context_window=capabilities.max_context_window,
            tool_type="chat",  # All Gemini models are chat tools
            cli="gemini",  # All Gemini models use Gemini CLI
        )
        blueprints.append(blueprint)

    # Register all blueprints
    register_blueprints(blueprints)


# Auto-register blueprints when this module is imported
_generate_and_register_blueprints()
