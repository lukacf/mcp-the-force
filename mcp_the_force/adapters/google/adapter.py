"""Protocol-based Gemini adapter using LiteLLM."""

import os
import logging
from typing import Any, Dict, List

from litellm import aresponses

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
        if hasattr(params, "structured_output_schema") and params.structured_output_schema:
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

    async def _handle_tool_calls(
        self,
        response: Any,
        tool_dispatcher: ToolDispatcher,
        conversation_input: List[Dict[str, Any]],
        request_params: Dict[str, Any],
    ) -> tuple[Any, List[Dict[str, Any]]]:
        """Handle Gemini-specific tool calls in the response.
        
        Gemini uses a different response format than the base implementation.
        """
        final_response = response
        updated_conversation = list(conversation_input)

        # Extract tool calls from Gemini response format
        tool_calls = []
        final_content = ""
        
        if hasattr(response, "output"):
            for item in response.output:
                if item.type == "message" and hasattr(item, "content"):
                    if isinstance(item.content, str):
                        final_content = item.content
                    elif isinstance(item.content, list):
                        for content_item in item.content:
                            if hasattr(content_item, "text"):
                                final_content = content_item.text
                elif item.type == "function_call":
                    tool_calls.append(item)

        # Process tool calls if present
        if tool_calls:
            logger.info(f"[GEMINI] Processing {len(tool_calls)} tool calls")

            # Add assistant message to conversation
            updated_conversation.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": final_content or ""}],
                }
            )

            # Execute tool calls and add results
            for tool_call in tool_calls:
                logger.info(f"[GEMINI] Executing tool: {tool_call.name}")
                try:
                    result = await tool_dispatcher.execute_tool(
                        tool_call.name,
                        tool_call.arguments,
                    )
                    updated_conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": str(result),
                        }
                    )
                except Exception as e:
                    logger.error(f"[GEMINI] Tool {tool_call.name} failed: {e}")
                    updated_conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": f"Error: {str(e)}",
                        }
                    )

            # Add minimal user message to continue (Gemini requires text)
            updated_conversation.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "text", "text": " "}],  # Single space
                }
            )

            # Continue conversation with tool results
            follow_up_params = {
                "model": request_params["model"],
                "input": updated_conversation,
            }

            # Copy auth params
            for key in ["vertex_project", "vertex_location", "api_key"]:
                if key in request_params:
                    follow_up_params[key] = request_params[key]

            logger.info("[GEMINI] Sending tool results")
            final_response = await aresponses(**follow_up_params)

        return final_response, updated_conversation

    def _extract_content(self, response: Any) -> str:
        """Extract content from Gemini-specific response format."""
        final_content = ""
        
        if hasattr(response, "output"):
            for item in response.output:
                if item.type == "message" and hasattr(item, "content"):
                    if isinstance(item.content, str):
                        final_content = item.content
                    elif isinstance(item.content, list):
                        for content_item in item.content:
                            if hasattr(content_item, "text"):
                                final_content = content_item.text
                                
        return final_content

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
