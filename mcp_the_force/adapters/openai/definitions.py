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
from ...utils.capability_formatter import format_capabilities


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
            "Supported by GPT-4 models and GPT-5.1 Codex. O-series models (o3, o3-pro, o4-mini) do not support this parameter. "
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
            "Supported by o-series models (o3, o3-pro, o4-mini), GPT-5.1 Codex, and GPT-5.1 Codex Max. Not supported by GPT-4 models. "
            "Syntax: A string, one of 'low', 'medium', 'high', or 'xhigh' (extra high - only for GPT-5.1 Codex Max). "
            "Default: 'medium' ('high' for o3-pro and gpt-5.1-codex, 'xhigh' for gpt-5.1-codex-max). "
            "Examples: reasoning_effort='high' (for gpt-5.1-codex), reasoning_effort='xhigh' (for gpt-5.1-codex-max)"
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
    native_vector_store_provider: Optional[str] = (
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
    max_context_window: int = (
        200_000  # Input limit: 200k + reasoning/output: 100k = 300k total
    )
    description: str = "Chain-of-thought reasoning with web search (200k input)"
    parallel_function_calls: int = -1  # Unlimited


@dataclass
class CodexMiniCapabilities(OSeriesCapabilities):
    """OpenAI codex-mini model capabilities (o4-mini optimized for coding)."""

    model_name: str = "codex-mini-latest"
    max_context_window: int = (
        200_000  # Input limit: 200k + reasoning/output: 100k = 300k total
    )
    description: str = "Lightweight code generator/completer for quick edits. Speed: very high. Tool use: limited. When to use: Inline edits, small bugs, scaffolding, regex/tests—avoid for multi-file refactors or repo-wide reasoning."
    parallel_function_calls: int = -1  # Unlimited
    supports_web_search: bool = False  # Codex-mini doesn't support web search
    supports_live_search: bool = False  # Codex-mini doesn't support live search
    web_search_tool: str = ""  # No web search tool for codex-mini
    native_vector_store_provider: Optional[str] = (
        None  # Codex-mini doesn't support file search
    )


@dataclass
class O3ProCapabilities(OSeriesCapabilities):
    """OpenAI o3-pro model capabilities."""

    model_name: str = "o3-pro"
    max_context_window: int = (
        200_000  # Input limit: 200k + reasoning/output: 100k = 300k total
    )
    description: str = "Heavyweight formal reasoner for deep, multi-step analysis. Speed: low. Tool use: very strong. When to use: Hard proofs/derivations, long-horizon planning, and safety-critical reviews where depth and rigor trump speed."
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
    description: str = "Long-context generalist with dependable tool use and low hallucination. Speed: medium. Tool use: strong. When to use: Large-corpus summarization, RAG across many docs, compliance reviews—choose when breadth > peak reasoning depth."
    web_search_tool: str = "web_search"
    parallel_function_calls: int = -1  # Unlimited


@dataclass
class DeepResearchCapabilities(OSeriesCapabilities):
    """Deep research model capabilities."""

    model_family: str = "research"
    force_background: bool = True  # Always background
    supports_streaming: bool = False
    supports_tools: bool = (
        False  # Deep research models don't support custom function calling tools
    )
    supports_web_search: bool = True  # Enable native web search tool (required)
    supports_live_search: bool = False  # No custom live search tools
    web_search_tool: str = "web_search_preview"  # Use native OpenAI web search tool
    parallel_function_calls: int = 0  # No function calling at all
    native_vector_store_provider: Optional[str] = (
        None  # No vector store provider - OpenAI handles natively
    )
    description: str = "Ultra-deep research with autonomous web search (30-60+ min)"


@dataclass
class O3DeepResearchCapabilities(DeepResearchCapabilities):
    """o3-deep-research model capabilities."""

    model_name: str = "o3-deep-research"
    max_context_window: int = 200_000
    description: str = "Autonomous browsing investigator for exhaustive, cited research. Runtime: 10-60 min. Speed: asynchronous. When to use: Due diligence, literature reviews, competitive analysis—when you need multi-source synthesis and auditability."


@dataclass
class O4MiniDeepResearchCapabilities(DeepResearchCapabilities):
    """o4-mini-deep-research model capabilities."""

    model_name: str = "o4-mini-deep-research"
    max_context_window: int = 200_000
    description: str = "Faster research agent for scoped, cited reconnaissance. Runtime: 2-10 min. Speed: asynchronous. When to use: Quick market scans, initial fact-finding, and follow-ups where time-to-first-brief matters more than depth."


@dataclass
class GPT51CodexCapabilities(OSeriesCapabilities):
    """GPT-5.1 Codex capabilities - updated superior coding/agent model."""

    model_family: str = "gpt-5.1-codex"
    model_name: str = "gpt-5.1-codex"
    max_context_window: int = 400_000  # 400k total context per OpenAI pricing page
    supports_reasoning_effort: bool = True
    supports_temperature: bool = (
        False  # Responses API forbids temperature for gpt-5.1-codex
    )
    supports_web_search: bool = True
    supports_live_search: bool = True
    web_search_tool: str = "web_search"
    parallel_function_calls: int = -1  # Unlimited parallel tool use
    default_reasoning_effort: str = "high"
    native_vector_store_provider: Optional[str] = (
        None  # GPT-5.1 Codex doesn't support file_search tool
    )
    description: str = (
        "Latest Codex-grade successor with 400k context and strong parallel tools. "
        "Use for complex refactors, multi-file synthesis, and long-horizon agents."
    )


@dataclass
class GPT51CodexMaxCapabilities(OSeriesCapabilities):
    """GPT-5.1 Codex Max capabilities - long-horizon agentic coding with compaction."""

    model_family: str = "gpt-5.1-codex-max"
    model_name: str = "gpt-5.1-codex-max"
    max_context_window: int = 400_000  # 400k total context per OpenAI pricing page
    supports_reasoning_effort: bool = True
    supports_temperature: bool = (
        False  # Responses API forbids temperature for gpt-5.1-codex-max
    )
    supports_web_search: bool = True
    supports_live_search: bool = True
    web_search_tool: str = "web_search"
    parallel_function_calls: int = -1  # Unlimited parallel tool use
    default_reasoning_effort: str = "xhigh"
    native_vector_store_provider: Optional[str] = (
        None  # GPT-5.1 Codex Max doesn't support file_search tool
    )
    description: str = (
        "Long-horizon agentic coding model with automatic compaction for 24+ hour tasks. "
        "77.9% on SWE-bench Verified at xhigh reasoning effort. "
        "30% fewer thinking tokens than GPT-5.1 Codex at same performance. "
        "Use for autonomous multi-day refactors, complex architectural changes, and sustained debugging sessions."
    )


@dataclass
class GPT5ProCapabilities(OSeriesCapabilities):
    """GPT-5 Pro capabilities — parity with GPT-5.1 Codex."""

    model_family: str = "gpt-5-pro"
    model_name: str = "gpt-5-pro"
    max_context_window: int = 400_000
    supports_reasoning_effort: bool = True
    supports_temperature: bool = (
        False  # Responses API forbids temperature for gpt-5 codex/pro
    )
    supports_web_search: bool = True
    supports_live_search: bool = True
    web_search_tool: str = "web_search"
    parallel_function_calls: int = -1
    default_reasoning_effort: str = "high"
    description: str = "GPT-5 Pro: flagship general/agentic model with 400k context, strong tool use, and coding parity with GPT-5.1 Codex."


# ====================================================================
# MODEL REGISTRY
# ====================================================================


def get_openai_model_capabilities():
    """Factory function to create fresh capability instances."""
    return {
        "o3": O3Capabilities(),
        "o3-pro": O3ProCapabilities(),
        "codex-mini": CodexMiniCapabilities(),
        "gpt-4.1": GPT41Capabilities(),
        "o3-deep-research": O3DeepResearchCapabilities(),
        "o4-mini-deep-research": O4MiniDeepResearchCapabilities(),
        "gpt-5.1-codex": GPT51CodexCapabilities(),
        "gpt-5.1-codex-max": GPT51CodexMaxCapabilities(),
        "gpt-5-pro": GPT5ProCapabilities(),
    }


def get_model_capability(model_name: str):
    """Get a fresh capability instance for a specific model."""
    capabilities = get_openai_model_capabilities()
    return capabilities.get(model_name)


# Create the registry using the factory function
OPENAI_MODEL_CAPABILITIES = get_openai_model_capabilities()


# ====================================================================
# BLUEPRINT GENERATION
# ====================================================================


def _calculate_timeout(model_name: str) -> int:
    """Calculate appropriate timeout for a model."""
    if "deep-research" in model_name:
        return 3600  # 1 hour for deep research
    elif model_name == "gpt-5.1-codex-max":
        return (
            5400  # 90 minutes for GPT-5.1 Codex Max (ultra long reasoning with xhigh)
        )
    elif model_name in {"gpt-5.1-codex", "gpt-5-pro"}:
        return 3000  # 50 minutes for GPT-5.1 Codex / GPT-5 Pro (long reasoning)
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
    # Check if OpenAI API key is available before registering any blueprints
    from ...config import get_settings
    import os
    from pydantic import SecretStr
    import logging

    logger = logging.getLogger(__name__)

    settings = get_settings()
    api_key = settings.openai_api_key
    logger.debug(
        f"[OPENAI_DEFINITIONS] Raw api_key: {type(api_key)}, present={bool(api_key)}"
    )

    if isinstance(api_key, SecretStr):
        api_key = api_key.get_secret_value()

    # Fallback to env-vars so tests can inject a key with monkeypatch.setenv
    env_key1 = os.getenv("OPENAI_API_KEY")
    env_key2 = os.getenv("MCP_OPENAI_API_KEY")
    logger.debug(
        f"[OPENAI_DEFINITIONS] Env vars: OPENAI_API_KEY={bool(env_key1)}, MCP_OPENAI_API_KEY={bool(env_key2)}"
    )

    api_key = api_key or env_key1 or env_key2
    logger.debug(
        f"[OPENAI_DEFINITIONS] Final api_key present: {bool(api_key and str(api_key).strip())}"
    )

    # Check if we're in mock mode - if so, allow registration without API key for test discoverability
    mock_mode = settings.adapter_mock  # Use config system instead of direct env var
    logger.debug(
        f"[OPENAI_DEFINITIONS] Mock mode check: settings.adapter_mock={mock_mode}, MCP_ADAPTER_MOCK={os.getenv('MCP_ADAPTER_MOCK')}"
    )

    if not (api_key and str(api_key).strip()) and not mock_mode:
        logger.debug(
            "[OPENAI_DEFINITIONS] Skipping registration: no API key and not in mock mode"
        )
        # Allow tests to proceed without a real key
        if os.getenv("PYTEST_CURRENT_TEST"):
            api_key = "test-openai-key"
        else:
            # No valid key and not in mock mode → skip registration and remove any existing OpenAI tools
            from ...tools.registry import TOOL_REGISTRY

            openai_tools_to_remove = []

            for tool_name, tool_meta in TOOL_REGISTRY.items():
                if tool_meta.model_config.get("adapter_class") == "openai":
                    openai_tools_to_remove.append(tool_name)

            for tool_name in openai_tools_to_remove:
                del TOOL_REGISTRY[tool_name]

            logger.debug(
                f"[OPENAI_DEFINITIONS] No API key found and not in mock mode, removed {len(openai_tools_to_remove)} OpenAI tools from registry"
            )
            return

    if mock_mode and not (api_key and str(api_key).strip()):
        logger.debug(
            f"[OPENAI_DEFINITIONS] Mock mode enabled, registering {len(OPENAI_MODEL_CAPABILITIES)} OpenAI tools for test discoverability (no API key required)"
        )
    else:
        logger.debug(
            f"[OPENAI_DEFINITIONS] API key found, registering {len(OPENAI_MODEL_CAPABILITIES)} OpenAI tools"
        )

    logger.warning(
        "[OPENAI_DEFINITIONS] Registering OpenAI blueprints: mock_mode=%s, api_key_present=%s, pytest=%s",
        mock_mode,
        bool(api_key),
        bool(os.getenv("PYTEST_CURRENT_TEST")),
    )

    blueprints = []

    # Only register supported models (excluding o3)
    supported_models = [
        "o3-pro",
        "codex-mini",
        "gpt-4.1",
        "o3-deep-research",
        "o4-mini-deep-research",
        "gpt-5.1-codex",
        "gpt-5.1-codex-max",
    ]

    for model_name, capabilities in OPENAI_MODEL_CAPABILITIES.items():
        if model_name not in supported_models:
            continue

        # Determine tool type based on model name
        if "deep-research" in model_name:
            tool_type = "research"
        else:
            tool_type = "chat"

        # Use friendly name for codex-mini
        tool_name = None
        if model_name == "codex-mini":
            tool_name = "codex_mini"  # Keep the friendly name
        elif model_name == "gpt-5.1-codex":
            # Preserve legacy tool id without extra underscore for 5.1
            tool_name = "gpt51_codex"
        elif model_name == "gpt-5.1-codex-max":
            # Consistent naming with gpt51_codex
            tool_name = "gpt51_codex_max"

        # Format capabilities and append to description
        capability_info = format_capabilities(capabilities)
        full_description = capabilities.description
        if capability_info:
            full_description = f"{capabilities.description} [{capability_info}]"

        blueprint = ToolBlueprint(
            model_name=model_name,
            adapter_key="openai",
            param_class=OpenAIToolParams,
            description=full_description,
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
