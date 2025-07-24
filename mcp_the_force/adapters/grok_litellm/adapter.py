"""Grok adapter implementation using LiteLLM."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import litellm
from litellm import aresponses

from mcp_the_force.adapters.base import BaseAdapter
from mcp_the_force.unified_session_cache import unified_session_cache
from ..tool_handler import ToolHandler

logger = logging.getLogger(__name__)

# Configure LiteLLM
litellm.set_verbose = False
litellm.drop_params = True


class GrokLiteLLMAdapter(BaseAdapter):
    """Grok adapter using LiteLLM's unified interface."""

    # Default model attributes (can be overridden by specific models)
    model_name = "grok-4"
    context_window = 256_000
    description_snippet = "Grok via LiteLLM"

    # Grok model capabilities
    CAPABILITIES = {
        "grok-4": {
            "context_window": 256_000,
            "supports_functions": True,
            "supports_live_search": True,
        },
        "grok-3-beta": {
            "context_window": 131_000,
            "supports_functions": True,
            "supports_live_search": True,
        },
    }

    def __init__(self, model: str):
        """Initialize Grok adapter with LiteLLM.

        Args:
            model: Grok model name (e.g., "grok-4", "grok-3-beta")
        """
        super().__init__()
        self.model_name = model

        # Get Grok-specific auth
        from mcp_the_force.config import get_settings

        settings = get_settings()

        # Get API key from xai provider config
        self.api_key = getattr(settings.xai, "api_key", None)
        if not self.api_key:
            raise ValueError("XAI_API_KEY not configured")

        # Get and set capabilities
        capabilities = self.CAPABILITIES.get(model, self.CAPABILITIES["grok-4"])
        self.context_window = capabilities["context_window"]
        self.supports_functions = capabilities["supports_functions"]
        self.supports_live_search = capabilities["supports_live_search"]

        # Initialize tool handler
        self.tool_handler = ToolHandler()

    async def generate(
        self,
        prompt: str,
        vector_store_ids: Optional[List[str]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        search_mode: Optional[str] = None,
        search_parameters: Optional[Dict[str, Any]] = None,
        return_citations: bool = True,
        structured_output_schema: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate a response using Grok via LiteLLM's Responses API."""
        try:
            # Initialize conversation_input in Responses API format
            conversation_input = []

            # Load session history if continuing
            if session_id:
                history = await unified_session_cache.get_history(session_id)
                if history:
                    # History is already in Responses API format
                    conversation_input = history
                    logger.debug(
                        f"Loaded {len(history)} items from session {session_id}"
                    )

            # Add new messages
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
            params: Dict[str, Any] = {
                "model": f"xai/{self.model_name}",  # Use xai/ prefix for LiteLLM
                "input": conversation_input,  # Responses API uses 'input'
                "api_key": self.api_key,
                "temperature": temperature,
            }

            # Note: xAI doesn't support previous_response_id, so we rely on history replay
            # The full conversation history is already included in messages

            # Add Live Search parameters for xAI
            search_params = {}
            if search_mode:
                search_params["mode"] = search_mode
                logger.info(f"Grok Live Search enabled: mode={search_mode}")
            if search_parameters:
                search_params.update(self._snake_case_params(search_parameters))
            if search_params:
                params["search_parameters"] = search_params
                logger.info(f"Grok Live Search parameters: {search_params}")

            # Add structured output
            if structured_output_schema:
                params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_response",
                        "schema": structured_output_schema,
                        "strict": True,
                    },
                }

            # Add tools
            tools = list(kwargs.get("tools", []))

            # Add built-in tools using openai type (Grok uses same format)
            built_in_declarations = self.tool_handler.prepare_tool_declarations(
                adapter_type="openai",
                vector_store_ids=vector_store_ids,
                disable_memory_search=kwargs.get("disable_memory_search", False),
            )
            tools.extend(built_in_declarations)

            if tools:
                params["tools"] = tools
                params["tool_choice"] = kwargs.get("tool_choice", "auto")

            # Tool calling loop for Responses API
            final_content = ""

            while True:
                # Make request
                response = await aresponses(**params)

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
                if session_id:
                    await unified_session_cache.set_history(
                        session_id, conversation_input
                    )
                    # Store that we're using responses API format
                    await unified_session_cache.set_api_format(session_id, "responses")
                    logger.debug(
                        f"Saved session {session_id} with {len(conversation_input)} items"
                    )

                # If no tool calls, we're done
                if not tool_calls:
                    break

                # Execute tool calls
                logger.debug(f"Executing {len(tool_calls)} tool calls")

                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    tool_args = json.loads(tool_call.arguments)

                    try:
                        output = await self.tool_handler.execute_tool_call(
                            tool_name=tool_name,
                            tool_args=tool_args,
                            vector_store_ids=vector_store_ids,
                            session_id=session_id,
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
                params["input"] = conversation_input

            # Extract citations if requested
            citations: List[Any] = []
            if return_citations and search_mode:
                # TODO: Extract citations from response metadata
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
