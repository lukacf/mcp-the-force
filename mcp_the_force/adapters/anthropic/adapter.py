"""Anthropic adapter implementation using LiteLLM."""

import logging
from typing import Dict, Any, List

from ..litellm_base import LiteLLMBaseAdapter
from ..capabilities import AdapterCapabilities
from .capabilities import ANTHROPIC_MODEL_CAPABILITIES
from .params import AnthropicToolParams

logger = logging.getLogger(__name__)


class AnthropicAdapter(LiteLLMBaseAdapter):
    """Adapter for Anthropic Claude models via LiteLLM."""

    param_class = AnthropicToolParams

    def __init__(self, model: str = "claude-opus-4-1-20250805"):
        """Initialize Anthropic adapter."""
        if model not in ANTHROPIC_MODEL_CAPABILITIES:
            raise ValueError(
                f"Unknown Anthropic model: {model}. "
                f"Supported models: {list(ANTHROPIC_MODEL_CAPABILITIES.keys())}"
            )

        self.model_name = model
        self.display_name = f"Anthropic {model}"
        self.capabilities = ANTHROPIC_MODEL_CAPABILITIES[model]

        super().__init__()

    @classmethod
    def get_supported_models(cls) -> Dict[str, type[AdapterCapabilities]]:
        """Get supported Anthropic models and their capabilities."""
        # Return type mapping for consistency with protocol
        return {k: type(v) for k, v in ANTHROPIC_MODEL_CAPABILITIES.items()}

    def _validate_environment(self) -> None:
        """Validate that Anthropic API key is configured."""
        from ...config import get_settings

        settings = get_settings()
        if not settings.anthropic.api_key:
            raise ValueError(
                "Anthropic API key not configured. "
                "Please set providers.anthropic.api_key in config.yaml or ANTHROPIC_API_KEY environment variable."
            )

    def _get_model_prefix(self) -> str:
        """Get the LiteLLM model prefix for Anthropic."""
        return "anthropic"

    def _build_request_params(
        self,
        conversation_input: List[Dict[str, Any]],
        params: Any,
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Build LiteLLM request parameters."""
        # Get base request params
        request_params: Dict[str, Any] = {
            "model": f"{self._get_model_prefix()}/{self.model_name}",
            "input": conversation_input,
        }

        # Add tools if provided
        if tools:
            request_params["tools"] = tools
            tool_choice = kwargs.get("tool_choice")
            if tool_choice:
                request_params["tool_choice"] = tool_choice

        # Add Anthropic-specific parameters
        if hasattr(params, "temperature"):
            request_params["temperature"] = params.temperature

        # Add required max_tokens
        if hasattr(params, "max_tokens"):
            request_params["max_tokens"] = params.max_tokens
        else:
            request_params["max_tokens"] = 4096  # Default

        # Handle extended thinking for Claude 4 models
        if self.capabilities.supports_reasoning_effort and hasattr(
            params, "get_thinking_budget"
        ):
            thinking_budget = params.get_thinking_budget()
            if thinking_budget:
                # LiteLLM translates thinking budget to Anthropic's format
                request_params["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                }

                # Always enable interleaved thinking for Claude 4 models
                if "extra_headers" not in request_params:
                    request_params["extra_headers"] = {}
                request_params["extra_headers"]["anthropic-beta"] = (
                    "interleaved-thinking-2025-05-14"
                )

                logger.debug(
                    f"Enabled extended thinking with budget: {thinking_budget} tokens"
                )

        # Handle structured output
        if (
            hasattr(params, "structured_output_schema")
            and params.structured_output_schema
        ):
            request_params["response_format"] = {
                "type": "json_schema",
                "json_schema": params.structured_output_schema,
            }

        return request_params

    def _extract_usage_info(self, response: Any) -> Dict[str, Any]:
        """Extract usage information from response."""
        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage_obj = response.usage
            usage["input_tokens"] = getattr(usage_obj, "prompt_tokens", 0)
            usage["output_tokens"] = getattr(usage_obj, "completion_tokens", 0)
            usage["total_tokens"] = getattr(usage_obj, "total_tokens", 0)

            # Extract thinking tokens if available
            if hasattr(usage_obj, "thinking_tokens"):
                usage["thinking_tokens"] = usage_obj.thinking_tokens

        return usage
