"""Protocol-based Gemini adapter using LiteLLM."""

import os
import asyncio
import logging
from typing import Any, Dict

import litellm
from litellm import aresponses

from ..protocol import CallContext, ToolDispatcher
from ..capabilities import AdapterCapabilities
from ...unified_session_cache import unified_session_cache
from .definitions import GeminiToolParams, GEMINI_MODEL_CAPABILITIES

logger = logging.getLogger(__name__)

# Configure LiteLLM
litellm.set_verbose = False
litellm.drop_params = True  # Drop unknown parameters


class GeminiAdapter:
    """Protocol-based Gemini adapter using LiteLLM.

    This adapter uses LiteLLM to communicate with Google's Gemini models via
    Vertex AI. LiteLLM handles all the complex type conversions and API
    specifics internally.
    """

    # Protocol requirements
    model_name: str
    display_name: str
    capabilities: AdapterCapabilities
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

        # Validate environment
        self._validate_environment()

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

        Args:
            prompt: The user's prompt
            params: Gemini-specific parameters
            ctx: Call context with session info
            tool_dispatcher: Tool dispatcher for function calling
            **kwargs: Additional parameters

        Returns:
            Dict with "content" key containing the response
        """
        # Build conversation input for the current turn only
        # The Responses API maintains conversation state via previous_response_id
        conversation_input = []

        # Add the user's prompt for this turn
        prompt_text = prompt

        # Add JSON formatting instruction when structured output is requested
        # The test already includes "respond ONLY with the JSON" in the prompt,
        # so we only add instruction if JSON is not mentioned
        if (
            hasattr(params, "structured_output_schema")
            and params.structured_output_schema
            and "json" not in prompt.lower()
        ):
            prompt_text = f"{prompt}\n\nRespond ONLY with valid JSON that matches the schema."

        conversation_input.append(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": prompt_text}],
            }
        )

        # Get tool declarations
        tools = []
        if tool_dispatcher:
            built_in_tools = tool_dispatcher.get_tool_declarations(
                capabilities=self.capabilities,
                disable_memory_search=getattr(params, "disable_memory_search", False),
            )
            tools.extend(built_in_tools)

        # Add any additional tools from kwargs
        if "tools" in kwargs:
            tools.extend(kwargs["tools"])

        # Build base parameters that are always included
        base_params = {
            "model": f"vertex_ai/{self.model_name}",  # LiteLLM provider prefix
            "temperature": getattr(params, "temperature", 1.0),
        }

        # Add Vertex AI configuration
        if os.getenv("VERTEX_PROJECT"):
            base_params["vertex_project"] = os.getenv("VERTEX_PROJECT")
        if os.getenv("VERTEX_LOCATION"):
            base_params["vertex_location"] = os.getenv("VERTEX_LOCATION")

        # Add API key if using direct Gemini API
        if os.getenv("GEMINI_API_KEY"):
            base_params["api_key"] = os.getenv("GEMINI_API_KEY")

        # Build initial request with all parameters for user turn
        request_params = {**base_params}
        request_params["input"] = conversation_input

        # Add instructions if provided
        if hasattr(params, "instructions") and params.instructions:
            request_params["instructions"] = params.instructions

        # Add previous_response_id for session continuation
        if ctx.session_id:
            previous_response_id = await unified_session_cache.get_metadata(
                ctx.session_id, "last_response_id"
            )
            if previous_response_id:
                request_params["previous_response_id"] = previous_response_id
                logger.info(
                    f"[GEMINI] Continuing session with previous_response_id: {previous_response_id}"
                )

        # Add tools if any (only for user turns)
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")

        # Add reasoning effort (LiteLLM translates to thinking budget)
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

        try:
            # Make the API call via LiteLLM Responses API
            logger.info(
                f"[GEMINI] Calling LiteLLM Responses API with model: {request_params['model']}"
            )
            response = await aresponses(**request_params)

            # Process response (Responses API format)
            final_content = ""
            tool_calls = []  # Re-initialize before parsing

            # Extract content and tool calls from response.output
            if hasattr(response, "output"):
                for item in response.output:
                    if item.type == "message":
                        # Extract content from message
                        if hasattr(item, "content"):
                            if isinstance(item.content, str):
                                final_content = item.content
                            elif isinstance(item.content, list):
                                # Handle list of content items
                                for content_item in item.content:
                                    if hasattr(content_item, "text"):
                                        final_content = content_item.text
                                    elif (
                                        hasattr(content_item, "type")
                                        and content_item.type == "text"
                                    ):
                                        final_content = content_item.text
                    elif item.type == "function_call":
                        tool_calls.append(item)

            # Handle function calls if present
            if tool_calls:
                logger.info(f"[GEMINI] Processing {len(tool_calls)} tool calls")

                # Execute tool calls
                tool_results = []
                for tool_call in tool_calls:
                    logger.info(f"[GEMINI] Executing tool: {tool_call.name}")
                    try:
                        result = await tool_dispatcher.execute(
                            tool_name=tool_call.name,
                            tool_args=tool_call.arguments,
                            context=ctx,
                        )
                        tool_results.append(
                            {
                                "type": "function_call_output",
                                "call_id": tool_call.call_id,
                                "output": str(result),
                            }
                        )
                    except Exception as e:
                        logger.error(
                            f"[GEMINI] Tool {tool_call.name} failed: {e}",
                            exc_info=True,
                        )
                        tool_results.append(
                            {
                                "type": "function_call_output",
                                "call_id": tool_call.call_id,
                                "output": f"Error: {str(e)}",
                            }
                        )

                # Create minimal follow-up request with ONLY required fields
                # Gemini requires at least one text message in the input
                follow_up_input = [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "text", "text": ""}
                        ],  # Empty text satisfies requirement
                    },
                    *tool_results,  # Add the function_call_output items
                ]

                follow_up_params = {
                    "model": base_params["model"],  # Use base model config
                    "input": follow_up_input,
                    "previous_response_id": response.id,
                }

                # Add Vertex AI/API key config from base_params
                if "vertex_project" in base_params:
                    follow_up_params["vertex_project"] = base_params["vertex_project"]
                if "vertex_location" in base_params:
                    follow_up_params["vertex_location"] = base_params["vertex_location"]
                if "api_key" in base_params:
                    follow_up_params["api_key"] = base_params["api_key"]

                logger.info(
                    f"[GEMINI] Sending tool results with previous_response_id: {response.id}"
                )

                response = await aresponses(**follow_up_params)

                # Process the follow-up response
                final_content = ""  # Reset content before parsing follow-up
                tool_calls = []  # Re-initialize to avoid processing stale calls

                if hasattr(response, "output"):
                    for item in response.output:
                        if item.type == "message" and hasattr(item, "content"):
                            if isinstance(item.content, str):
                                final_content = item.content
                            elif isinstance(item.content, list):
                                for content_item in item.content:
                                    if hasattr(content_item, "text"):
                                        final_content = content_item.text

            # Save the response ID for session continuation
            if ctx.session_id and hasattr(response, "id"):
                await unified_session_cache.set_metadata(
                    ctx.session_id, "last_response_id", response.id
                )
                # Store API format for compatibility
                await unified_session_cache.set_api_format(ctx.session_id, "responses")
                logger.info(
                    f"[GEMINI] Saved response_id {response.id} for session {ctx.session_id}"
                )

            # Return response
            return {
                "content": final_content,
                "citations": None,  # Gemini doesn't have Live Search like Grok
            }

        except asyncio.CancelledError:
            logger.warning("[GEMINI] Request cancelled")
            raise
        except Exception as e:
            logger.error(
                f"[GEMINI] Error in generate: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            raise
