"""Protocol-based Gemini adapter using LiteLLM."""

import os
import logging
from typing import Any, Dict, List


from ..litellm_base import LiteLLMBaseAdapter
from ..protocol import CallContext, ToolDispatcher
from .definitions import GeminiToolParams, GEMINI_MODEL_CAPABILITIES

logger = logging.getLogger(__name__)


class GeminiAdapter(LiteLLMBaseAdapter):
    """Protocol-based Gemini adapter using LiteLLM.

    This adapter uses LiteLLM to communicate with Google's Gemini models via
    Vertex AI. LiteLLM handles all the complex type conversions and API
    specifics internally.
    """

    param_class = GeminiToolParams

    def __init__(self, model: str = "gemini-2.5-pro"):
        """Initialize the Gemini adapter.

        Args:
            model: Model name (e.g., "gemini-2.5-pro", "gemini-2.5-flash")
        """
        if model not in GEMINI_MODEL_CAPABILITIES:
            raise ValueError(f"Unsupported Gemini model: {model}")

        self.model_name = model
        self.display_name = f"Gemini {model} (LiteLLM)"
        self.capabilities = GEMINI_MODEL_CAPABILITIES[model]

        # Call parent init after setting required attributes
        super().__init__()

    def _validate_environment(self):
        """Ensure required environment variables are set."""
        # Check for Vertex AI configuration
        if os.getenv("VERTEX_PROJECT") and os.getenv("VERTEX_LOCATION"):
            logger.info("Using Vertex AI configuration")
        # Check for direct Gemini API key
        elif os.getenv("GEMINI_API_KEY"):
            logger.info("Using Gemini API key")
        else:
            logger.warning(
                "No Gemini/Vertex AI credentials found. Set either "
                "VERTEX_PROJECT/VERTEX_LOCATION or GEMINI_API_KEY"
            )

    def _get_model_prefix(self) -> str:
        """Get the LiteLLM model prefix for this provider."""
        return "vertex_ai"

    def _build_request_params(
        self,
        conversation_input: List[Dict[str, Any]],
        params: GeminiToolParams,
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Build Gemini-specific request parameters."""
        # Build base parameters
        request_params = {
            "model": f"{self._get_model_prefix()}/{self.model_name}",
            "input": conversation_input,
            "temperature": getattr(params, "temperature", 1.0),
        }

        # Add Vertex AI configuration
        if os.getenv("VERTEX_PROJECT"):
            request_params["vertex_project"] = os.getenv("VERTEX_PROJECT")
        if os.getenv("VERTEX_LOCATION"):
            request_params["vertex_location"] = os.getenv("VERTEX_LOCATION")

        # Add API key if using direct Gemini API
        if os.getenv("GEMINI_API_KEY"):
            request_params["api_key"] = os.getenv("GEMINI_API_KEY")

        # Add instructions if provided
        if hasattr(params, "instructions") and params.instructions:
            request_params["instructions"] = params.instructions

        # Add tools if any
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")

        # Add reasoning effort
        if hasattr(params, "reasoning_effort") and params.reasoning_effort:
            request_params["reasoning_effort"] = params.reasoning_effort
            logger.info(f"[GEMINI] Using reasoning_effort: {params.reasoning_effort}")

        # Add structured output schema
        if (
            hasattr(params, "structured_output_schema")
            and params.structured_output_schema
        ):
            request_params["response_format"] = {
                "type": "json_object",
                "response_schema": params.structured_output_schema,
                "enforce_validation": True,
            }
            logger.info("[GEMINI] Using structured output schema")

        # Add any extra kwargs that LiteLLM might use
        for key in ["max_tokens", "top_p", "frequency_penalty", "presence_penalty"]:
            if key in kwargs:
                request_params[key] = kwargs[key]

        return request_params

    async def generate(
        self,
        prompt: str,
        params: GeminiToolParams,
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate a response using LiteLLM.

        Uses the base implementation with Gemini-specific overrides.
        """
        # Gemini doesn't support citations, so we override the result
        result = await super().generate(
            prompt=prompt,
            params=params,
            ctx=ctx,
            tool_dispatcher=tool_dispatcher,
            **kwargs,
        )

        # Ensure we don't return citations for Gemini
        result["citations"] = None
        return result
