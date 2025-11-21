"""Protocol-based Grok adapter using LiteLLM.

This adapter implements the MCPAdapter protocol without inheritance,
following the architectural design in docs/litellm-refactor.md.
"""

import logging
from typing import Any, Dict, List

import litellm

from ..errors import InvalidModelException
from ..litellm_base import LiteLLMBaseAdapter
from ..protocol import CallContext, ToolDispatcher
from .definitions import GrokToolParams, GROK_MODEL_CAPABILITIES

logger = logging.getLogger(__name__)

# Configure LiteLLM
litellm.set_verbose = False
litellm.drop_params = True


class GrokAdapter(LiteLLMBaseAdapter):
    """Grok adapter implementing MCPAdapter protocol.

    This adapter uses LiteLLM's Responses API internally and supports
    all xAI Grok models with their specific capabilities.
    """

    def __init__(self, model: str):
        """Initialize Grok adapter.

        Args:
            model: Grok model name (e.g., "grok-4.1", "grok-3-beta")

        Raises:
            ValueError: If model is not supported
        """
        if model not in GROK_MODEL_CAPABILITIES:
            raise InvalidModelException(
                model=model,
                supported_models=list(GROK_MODEL_CAPABILITIES.keys()),
                provider="Grok",
            )

        self.model_name = model
        self.display_name = f"Grok {model} (LiteLLM)"
        self.param_class = GrokToolParams

        # Get pre-built capabilities for this model
        self.capabilities = GROK_MODEL_CAPABILITIES[model]

        # Self-contained authentication
        self._setup_auth()

    def _setup_auth(self):
        """Set up authentication from settings."""
        from ...config import get_settings

        settings = get_settings()

        # Get API key from xai provider config
        self.api_key = getattr(settings.xai, "api_key", None)
        if not self.api_key:
            raise ValueError(
                "XAI_API_KEY not configured. Please add your xAI API key to "
                "secrets.yaml or set XAI_API_KEY environment variable."
            )

    def _get_model_prefix(self) -> str:
        """Get the LiteLLM model prefix for this provider."""
        return "xai"

    def _snake_case_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Convert camelCase keys to snake_case for Grok API."""
        result = {}
        for key, value in params.items():
            # Convert camelCase to snake_case
            snake_key = ""
            for i, char in enumerate(key):
                if i > 0 and char.isupper():
                    snake_key += "_" + char.lower()
                else:
                    snake_key += char.lower()
            result[snake_key] = value
        return result

    def _convert_messages_to_input(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert chat format messages to Responses API input format."""
        conversation_input = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role in ["system", "user", "assistant"]:
                # Convert to Responses API format
                conversation_input.append(
                    {
                        "type": "message",
                        "role": role,
                        "content": [{"type": "text", "text": content}],
                    }
                )
            elif role == "tool":
                # Convert tool response to function_call_output
                conversation_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": msg.get("tool_call_id", ""),
                        "output": content,
                    }
                )

        return conversation_input

    def _build_request_params(
        self,
        conversation_input: List[Dict[str, Any]],
        params: GrokToolParams,
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Build Grok-specific request parameters."""
        # Build base parameters
        request_params = {
            "model": f"{self._get_model_prefix()}/{self.model_name}",
            "input": conversation_input,
            "api_key": self.api_key,
            "temperature": getattr(params, "temperature", 0.7),
        }

        # Add reasoning effort for supported models
        # Note: Grok only supports "low" or "high", not "medium"
        if self.capabilities.supports_reasoning_effort and getattr(
            params, "reasoning_effort", None
        ):
            # Map medium to high for Grok
            effort = getattr(params, "reasoning_effort", None)
            if effort == "medium":
                effort = "high"
            request_params["reasoning_effort"] = effort

        # Add Live Search parameters for xAI
        search_params = {}
        search_mode = getattr(params, "search_mode", None)
        if search_mode:
            search_params["mode"] = search_mode
            logger.info(f"Grok Live Search enabled: mode={search_mode}")
        search_parameters = getattr(params, "search_parameters", None)
        if search_parameters:
            search_params.update(self._snake_case_params(search_parameters))
        if search_params:
            request_params["search_parameters"] = search_params
            logger.info(f"Grok Live Search parameters: {search_params}")

        # Add structured output
        structured_output_schema = getattr(params, "structured_output_schema", None)
        if structured_output_schema:
            request_params["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "schema": structured_output_schema,
                    "strict": True,
                },
            }

        # Add tools if any
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")
            logger.info(f"[GROK_TOOLS] Passing {len(tools)} tools to LiteLLM")
            for tool in tools:
                tool_name = tool.get(
                    "name", tool.get("function", {}).get("name", "unknown")
                )
                logger.info(f"[GROK_TOOL] - {tool_name}")

        return request_params

    def _add_provider_specific_data(
        self, response: Any, params: GrokToolParams
    ) -> Dict[str, Any]:
        """Add Grok-specific data to the response."""
        # Extract citations if requested
        citations: List[Any] = []
        if getattr(params, "return_citations", True) and getattr(
            params, "search_mode", None
        ):
            # TODO: Extract citations from response metadata
            # Grok returns citations in the response somewhere
            pass

        return {"citations": citations if citations else None}

    async def generate(
        self,
        prompt: str,
        params: GrokToolParams,
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate response using LiteLLM's Responses API.

        Uses the base implementation from LiteLLMBaseAdapter.
        """
        return await super().generate(
            prompt=prompt,
            params=params,
            ctx=ctx,
            tool_dispatcher=tool_dispatcher,
            **kwargs,
        )
