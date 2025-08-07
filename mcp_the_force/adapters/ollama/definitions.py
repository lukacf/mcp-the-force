"""Single source of truth for Ollama adapter definitions.

This file contains all the model definitions, capabilities, parameters, and blueprint
generation logic for the Ollama adapter.
"""

from typing import Optional
from dataclasses import dataclass

from ..params import BaseToolParams
from ..capabilities import AdapterCapabilities
from ...tools.descriptors import Route
from ...tools.blueprint import ToolBlueprint
from ...tools.blueprint_registry import register_blueprints


# ====================================================================
# PARAMETER CLASS WITH CAPABILITY REQUIREMENTS
# ====================================================================


class OllamaToolParams(BaseToolParams):  # type: ignore[misc]
    """Ollama-specific parameters."""

    temperature: float = Route.adapter(  # type: ignore[assignment]
        default=0.7,
        description=(
            "(Optional) Sampling temperature (0.0-2.0). Lower values are more deterministic. "
            "Syntax: A float, typically between 0.0 and 2.0. "
            "Default: 0.7. "
            "Example: temperature=0.3"
        ),
    )

    max_tokens: Optional[int] = Route.adapter(  # type: ignore[assignment]
        default=1024,
        description="Maximum tokens to generate. None for model default.",
    )

    keep_alive: Optional[str] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description="How long to keep model loaded (e.g. '5m', '2h', '-1' for indefinite)",
    )

    format: Optional[str] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description="Response format. Use 'json' for JSON mode.",
    )

    seed: Optional[int] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description="Random seed for reproducible outputs",
    )

    top_p: Optional[float] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description="Nucleus sampling threshold (0.0-1.0)",
    )

    top_k: Optional[int] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description="Top-k sampling parameter",
    )

    repeat_penalty: Optional[float] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description="Penalty for repeating tokens (1.0 = no penalty)",
    )


# ====================================================================
# CAPABILITY DEFINITIONS
# ====================================================================


@dataclass
class OllamaBaseCapabilities(AdapterCapabilities):
    """Base capabilities shared by all Ollama models."""

    provider: str = "ollama"
    model_family: str = "local_llm"
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_temperature: bool = True
    supports_structured_output: bool = (
        False  # Local models don't support schema validation
    )
    supports_reasoning: bool = False
    supports_vision: bool = False
    supports_prefill: bool = False
    supports_computer_use: bool = False
    supports_web_search: bool = False
    supports_n: bool = False
    supports_stop_sequences: bool = True

    # Local models don't have built-in vector stores
    native_vector_store_provider: Optional[str] = None

    # Pricing - local models are free to run
    price_per_million_input_tokens: float = 0.0
    price_per_million_output_tokens: float = 0.0


@dataclass
class GptOss20bCapabilities(OllamaBaseCapabilities):
    """Capabilities for gpt-oss:20b model."""

    model_name: str = "gpt-oss:20b"
    max_context_window: int = 32768  # Conservative default
    description: str = "gpt-oss:20b (20.9B)"


@dataclass
class GptOss120bCapabilities(OllamaBaseCapabilities):
    """Capabilities for gpt-oss:120b model."""

    model_name: str = "gpt-oss:120b"
    max_context_window: int = 32768  # Conservative default
    description: str = "gpt-oss:120b (116.8B)"


# ====================================================================
# MODEL CAPABILITIES REGISTRY
# ====================================================================

OLLAMA_MODEL_CAPABILITIES = {
    "gpt-oss:20b": GptOss20bCapabilities(),
    "gpt-oss:120b": GptOss120bCapabilities(),
}


# ====================================================================
# BLUEPRINT GENERATION
# ====================================================================


def _calculate_timeout(model_name: str) -> int:
    """Calculate appropriate timeout for a model."""
    if "120b" in model_name:
        return 600  # 10 minutes for larger models
    else:
        return 300  # 5 minutes for smaller models


def _get_friendly_name(model_name: str) -> str:
    """Generate a friendly tool name from the model name.

    Examples:
    - 'gpt-oss:20b' -> 'chat_with_gpt_oss_20b'
    - 'gpt-oss:120b' -> 'chat_with_gpt_oss_120b'
    """
    # Replace colons and hyphens with underscores
    clean_name = model_name.replace(":", "_").replace("-", "_")
    return f"chat_with_{clean_name}"


def _generate_and_register_blueprints():
    """Generate and register blueprints for all Ollama models."""
    blueprints = []

    for model_name, capabilities in OLLAMA_MODEL_CAPABILITIES.items():
        blueprint = ToolBlueprint(
            model_name=model_name,
            tool_name=_get_friendly_name(model_name),
            adapter_key="ollama",
            param_class=OllamaToolParams,
            description=capabilities.description,
            timeout=_calculate_timeout(model_name),
            context_window=capabilities.max_context_window,
            tool_type="chat",  # All Ollama models are chat tools
        )
        blueprints.append(blueprint)

    # Register all blueprints
    register_blueprints(blueprints)


# Auto-register blueprints when this module is imported
_generate_and_register_blueprints()
