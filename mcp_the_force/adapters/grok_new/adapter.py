"""Protocol-based Grok adapter using LiteLLM.

This adapter implements the MCPAdapter protocol without inheritance,
following the architectural design in docs/litellm-refactor.md.
"""

import asyncio
import logging
from typing import Any, Dict, List

import litellm
from litellm import aresponses

from ..params import GrokToolParams
from ..protocol import CallContext, ToolDispatcher
from ...unified_session_cache import unified_session_cache
from .models import GROK_MODEL_CAPABILITIES

logger = logging.getLogger(__name__)

# Configure LiteLLM
litellm.set_verbose = False
litellm.drop_params = True


class GrokAdapter:
    """Grok adapter implementing MCPAdapter protocol.

    This adapter uses LiteLLM's Responses API internally and supports
    all xAI Grok models with their specific capabilities.
    """

    def __init__(self, model: str):
        """Initialize Grok adapter.

        Args:
            model: Grok model name (e.g., "grok-4", "grok-3-beta")

        Raises:
            ValueError: If model is not supported
        """
        if model not in GROK_MODEL_CAPABILITIES:
            raise ValueError(
                f"Unknown Grok model: {model}. "
                f"Supported models: {list(GROK_MODEL_CAPABILITIES.keys())}"
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

        Args:
            prompt: User prompt
            params: Validated GrokToolParams instance
            ctx: Call context with session_id and vector_store_ids
            tool_dispatcher: Tool execution interface
            **kwargs: Additional parameters (e.g., messages for continuation)

        Returns:
            Dict with "content" and optionally "citations"
        """
        try:
            # Initialize conversation_input in Responses API format
            conversation_input = []

            # Load session history if continuing
            if ctx.session_id:
                history = await unified_session_cache.get_history(ctx.session_id)
                if history:
                    # History is already in Responses API format
                    conversation_input = history
                    logger.debug(
                        f"Loaded {len(history)} items from session {ctx.session_id}"
                    )

            # Add new messages
            messages = kwargs.get("messages")
            if messages:
                # Convert provided messages to Responses API format
                conversation_input.extend(self._convert_messages_to_input(messages))
                # Add new user message
                conversation_input.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}],
                    }
                )
            else:
                # Build new conversation
                system_instruction = kwargs.get("system_instruction")
                if system_instruction:
                    conversation_input.append(
                        {
                            "type": "message",
                            "role": "system",
                            "content": [{"type": "text", "text": system_instruction}],
                        }
                    )
                conversation_input.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}],
                    }
                )

            # Build request parameters for Responses API
            request_params: Dict[str, Any] = {
                "model": f"xai/{self.model_name}",  # LiteLLM needs provider prefix
                "input": conversation_input,  # Responses API uses 'input'
                "api_key": self.api_key,
                "temperature": params.temperature,
            }

            # Add reasoning effort for supported models (not Grok 4!)
            # Note: Grok only supports "low" or "high", not "medium"
            if (
                self.capabilities.supports_reasoning_effort
                and params.reasoning_effort
                and self.model_name != "grok-4"
            ):  # Grok 4 doesn't support it
                # Map medium to high for Grok
                effort = params.reasoning_effort
                if effort == "medium":
                    effort = "high"
                request_params["reasoning_effort"] = effort

            # Add Live Search parameters for xAI
            search_params = {}
            if params.search_mode:
                search_params["mode"] = params.search_mode
                logger.info(f"Grok Live Search enabled: mode={params.search_mode}")
            if params.search_parameters:
                search_params.update(self._snake_case_params(params.search_parameters))
            if search_params:
                request_params["search_parameters"] = search_params
                logger.info(f"Grok Live Search parameters: {search_params}")

            # Add structured output
            if params.structured_output_schema:
                request_params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_response",
                        "schema": params.structured_output_schema,
                        "strict": True,
                    },
                }

            # Add tools if needed
            tools = []

            # Get built-in tools (including search_project_history)
            disable_memory_search = (
                params.disable_memory_search
                if hasattr(params, "disable_memory_search")
                else False
            )
            built_in_tools = tool_dispatcher.get_tool_declarations(
                adapter_type="grok",  # Must be "grok" to get search_task_files
                disable_memory_search=disable_memory_search,
            )
            tools.extend(built_in_tools)

            # Add any extra tools passed in
            extra_tools = kwargs.get("tools", [])
            tools.extend(extra_tools)

            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = kwargs.get("tool_choice", "auto")
                logger.info(f"[GROK_TOOLS] Passing {len(tools)} tools to LiteLLM")
                for tool in tools:
                    tool_name = tool.get("function", {}).get("name", "unknown")
                    logger.info(f"[GROK_TOOL] - {tool_name}")

            # Tool calling loop for Responses API
            final_content = ""

            while True:
                # Make request
                response = await aresponses(**request_params)

                # Process response (Responses API format)
                tool_calls = []

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
                                # Add assistant message to conversation_input
                                conversation_input.append(
                                    {
                                        "type": "message",
                                        "role": "assistant",
                                        "content": [
                                            {"type": "text", "text": final_content}
                                        ],
                                    }
                                )
                        elif item.type == "function_call":
                            tool_calls.append(item)

                # Save the full conversation history in Responses API format
                if ctx.session_id:
                    await unified_session_cache.set_history(
                        ctx.session_id, conversation_input
                    )
                    # Store that we're using responses API format
                    await unified_session_cache.set_api_format(
                        ctx.session_id, "responses"
                    )
                    logger.debug(
                        f"Saved session {ctx.session_id} with {len(conversation_input)} items"
                    )

                # If no tool calls, we're done
                if not tool_calls:
                    break

                # Execute tool calls
                logger.debug(f"Executing {len(tool_calls)} tool calls")

                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    logger.info(f"[GROK_EXEC] Executing tool: {tool_name}")
                    tool_args = tool_call.arguments  # Already a string

                    try:
                        output = await tool_dispatcher.execute(
                            tool_name=tool_name, tool_args=tool_args, context=ctx
                        )
                    except Exception as e:
                        output = f"Error executing tool '{tool_name}': {e}"
                        logger.error(f"Tool execution error: {e}")

                    # Add tool result to conversation_input for next iteration
                    tool_result_item = {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": str(output),
                    }
                    conversation_input.append(tool_result_item)

                # Continue the loop with tool results
                # Update params with new conversation_input
                request_params["input"] = conversation_input

            # Extract citations if requested
            citations: List[Any] = []
            if params.return_citations and params.search_mode:
                # TODO: Extract citations from response metadata
                # Grok returns citations in the response somewhere
                pass

            return {
                "content": final_content,
                "citations": citations if citations else None,
            }

        except asyncio.CancelledError:
            logger.info("Grok request cancelled")
            raise
        except Exception as e:
            logger.error(f"Grok adapter error: {e}")
            raise RuntimeError(f"Grok generation failed: {str(e)}") from e
