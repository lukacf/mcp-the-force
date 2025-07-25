"""Protocol-based Gemini adapter using LiteLLM."""

import os
import asyncio
import logging
from typing import Any, Dict

import litellm
from litellm import acompletion

from ..params import GeminiToolParams
from ..protocol import CallContext, ToolDispatcher
from ..capabilities import AdapterCapabilities
from ...unified_session_cache import unified_session_cache
from .models import GEMINI_MODEL_CAPABILITIES

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
        # Load session history
        history = []
        if ctx.session_id:
            history = await unified_session_cache.get_history(ctx.session_id)
            logger.info(
                f"[GEMINI] Loaded {len(history)} messages from session {ctx.session_id}"
            )

        # Build messages in OpenAI format
        messages = history + [{"role": "user", "content": prompt}]

        # Get tool declarations
        tools = []
        if tool_dispatcher:
            built_in_tools = tool_dispatcher.get_tool_declarations(
                adapter_type="grok",  # Use "grok" to get OpenAI format + search_task_files
                disable_memory_search=getattr(params, "disable_memory_search", False),
            )
            tools.extend(built_in_tools)

        # Add any additional tools from kwargs
        if "tools" in kwargs:
            tools.extend(kwargs["tools"])

        # Build request parameters
        request_params = {
            "model": f"vertex_ai/{self.model_name}",  # LiteLLM provider prefix
            "messages": messages,
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

        # Add tools if any
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
            # Make the API call via LiteLLM
            logger.info(
                f"[GEMINI] Calling LiteLLM with model: {request_params['model']}"
            )
            response = await acompletion(**request_params)

            # Extract the response
            response_message = response.choices[0].message

            # Handle function calls if present
            if hasattr(response_message, "tool_calls") and response_message.tool_calls:
                logger.info(
                    f"[GEMINI] Processing {len(response_message.tool_calls)} tool calls"
                )

                # Convert response to dict for history
                messages.append(response_message.model_dump())

                # Execute tool calls
                tool_results = []
                for tool_call in response_message.tool_calls:
                    logger.info(f"[GEMINI] Executing tool: {tool_call.function.name}")
                    try:
                        result = await tool_dispatcher.execute(
                            tool_name=tool_call.function.name,
                            tool_args=tool_call.function.arguments,
                            context=ctx,
                        )
                        tool_results.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": tool_call.function.name,
                                "content": str(result),
                            }
                        )
                    except Exception as e:
                        logger.error(
                            f"[GEMINI] Tool {tool_call.function.name} failed: {e}",
                            exc_info=True,
                        )
                        tool_results.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": tool_call.function.name,
                                "content": f"Error: {str(e)}",
                            }
                        )

                # Add tool results to messages
                messages.extend(tool_results)

                # Continue the conversation with tool results
                request_params["messages"] = messages
                response = await acompletion(**request_params)
                response_message = response.choices[0].message

            # Get the final content
            content = response_message.content or ""

            # Save updated history
            messages.append(response_message.model_dump())
            if ctx.session_id:
                await unified_session_cache.set_history(ctx.session_id, messages)
                # Store API format for compatibility
                await unified_session_cache.set_api_format(ctx.session_id, "chat")
                logger.info(
                    f"[GEMINI] Saved {len(messages)} messages to session {ctx.session_id}"
                )

            # Return response
            return {
                "content": content,
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
