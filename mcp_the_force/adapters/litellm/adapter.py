"""LiteLLM adapter for testing unified LLM interface."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import litellm
from litellm import aresponses

from mcp_the_force.adapters.base import BaseAdapter
from ..tool_handler import ToolHandler

logger = logging.getLogger(__name__)

# Configure LiteLLM
litellm.set_verbose = False  # Set to True for debugging
litellm.drop_params = True  # Drop unsupported params instead of erroring


class LiteLLMAdapter(BaseAdapter):
    """Test adapter using LiteLLM unified interface."""

    model_name = "gpt-4o"  # Testing with gpt-4o for fast responses
    context_window = 128000
    description_snippet = "LiteLLM unified adapter test with gpt-4o"

    def __init__(self, model: str):
        """Initialize the LiteLLM adapter.

        Args:
            model: Model name (used for compatibility with factory)
        """
        super().__init__()
        # Override with our test model
        self.model_name = "gpt-4o"

        # Get API key from settings
        from mcp_the_force.config import get_settings

        settings = get_settings()
        self.api_key = settings.openai_api_key
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        # Initialize tool handler for built-in tools
        self.tool_handler = ToolHandler()

    async def generate(
        self,
        prompt: str,
        vector_store_ids: Optional[List[str]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        reasoning_effort: Optional[str] = None,
        structured_output_schema: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate a response using LiteLLM's Responses API."""
        try:
            # Build initial messages
            if messages is None:
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

            # Prepare parameters for Responses API
            params: Dict[str, Any] = {
                "model": f"openai/{self.model_name}",  # LiteLLM needs provider prefix
                "input": messages,  # Responses API uses 'input' not 'messages'
                "api_key": self.api_key,
                "temperature": temperature,
                "truncation": "auto",  # Recommended for long conversations
            }

            # Handle session continuation
            previous_response_id = kwargs.get("previous_response_id")
            if previous_response_id:
                params["previous_response_id"] = previous_response_id

            # Note: reasoning_effort is not supported by gpt-4o, will be dropped by LiteLLM

            # Add structured output if provided
            if structured_output_schema:
                params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_response",
                        "schema": structured_output_schema,
                        "strict": True,
                    },
                }

            # Add tools if provided
            tools = list(kwargs.get("tools", []))  # Make a copy

            # Add built-in tools using ToolHandler
            # Since we're using gpt-4o (OpenAI model), use "openai" adapter type
            # This ensures we get native file_search instead of search_task_files
            built_in_declarations = self.tool_handler.prepare_tool_declarations(
                adapter_type="openai",  # Use openai type for OpenAI models
                vector_store_ids=vector_store_ids,
                disable_memory_search=kwargs.get("disable_memory_search", False),
            )

            # Add built-in tools directly (they already have the correct format)
            tools.extend(built_in_declarations)

            if tools:
                params["tools"] = tools
                params["tool_choice"] = kwargs.get("tool_choice", "auto")

            # Filter out our custom parameters that OpenAI doesn't understand
            # These are handled by our framework, not passed to the LLM
            excluded_params = {
                "instructions",
                "output_format",
                "context",
                "session_id",
                "disable_memory_search",
                "priority_context",
                "attachments",
                "tools",
                "tool_choice",
                "timeout",
                "previous_response_id",
            }

            # Add any extra parameters that aren't excluded
            for key, value in kwargs.items():
                if key not in params and key not in excluded_params:
                    params[key] = value

            # Log the request
            logger.debug(
                f"LiteLLM Responses API request: model={self.model_name}, temperature={temperature}, previous_response_id={previous_response_id}"
            )

            # Tool calling loop - keep calling until no more tool calls
            session_id = kwargs.get("session_id")
            conversation_input = messages.copy()  # Start with initial messages
            final_response = None

            while True:
                # Update input for current iteration
                params["input"] = conversation_input

                # Make the request with cancellation support
                try:
                    if stream:
                        raise NotImplementedError(
                            "Streaming not implemented in test adapter"
                        )
                    else:
                        response = await aresponses(**params)

                except asyncio.CancelledError:
                    logger.info("LiteLLM request cancelled")
                    raise

                # Wait for completion if in background mode
                if hasattr(response, "status") and response.status in [
                    "in_progress",
                    "pending",
                ]:
                    logger.debug(
                        "Response in background mode, polling for completion..."
                    )

                    # Poll for completion
                    while response.status in ["in_progress", "pending"]:
                        await asyncio.sleep(1)  # Wait 1 second between polls

                        try:
                            response = await litellm.aresponses.retrieve(response.id)
                        except AttributeError:
                            logger.warning(
                                "LiteLLM doesn't support retrieve, hoping response updates itself"
                            )
                            break

                # Process response output items
                output_items = response.output or []
                tool_calls = []
                content_parts = []

                for item in output_items:
                    # Check for tool calls
                    if hasattr(item, "type") and item.type == "function_call":
                        tool_calls.append(item)
                    # Check for message content
                    elif hasattr(item, "type") and item.type == "message":
                        if hasattr(item, "content") and item.content:
                            for content_item in item.content:
                                if hasattr(content_item, "text") and content_item.text:
                                    content_parts.append(content_item.text)

                # If no tool calls, we're done
                if not tool_calls:
                    final_response = response
                    break

                # Execute tool calls
                logger.debug(f"Executing {len(tool_calls)} tool calls")
                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    tool_args = json.loads(tool_call.arguments or "{}")

                    try:
                        # Use ToolHandler for built-in tools
                        output = await self.tool_handler.execute_tool_call(
                            tool_name=tool_name,
                            tool_args=tool_args,
                            vector_store_ids=vector_store_ids,
                            session_id=session_id,
                        )
                    except Exception as e:
                        output = f"Error executing tool '{tool_name}': {e}"
                        logger.error(f"Tool execution error: {e}")

                    # Convert tool call to dict format for the conversation
                    conversation_input.append(
                        {
                            "type": "function_call",
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                            "call_id": tool_call.call_id,
                        }
                    )

                    # Add tool result to conversation in Responses API format
                    conversation_input.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": str(output),
                        }
                    )

                # Continue with the next iteration
                # Remove previous_response_id for follow-up calls in the same turn
                if "previous_response_id" in params:
                    del params["previous_response_id"]

            # Extract final content from the last response
            content_parts = []
            if final_response and hasattr(final_response, "output"):
                for item in final_response.output:
                    if hasattr(item, "type") and item.type == "message":
                        if hasattr(item, "content") and item.content:
                            for content_item in item.content:
                                if hasattr(content_item, "text") and content_item.text:
                                    content_parts.append(content_item.text)

            content = "\n".join(content_parts) if content_parts else ""

            # Build final result
            result = {
                "content": content,
                "response_id": final_response.id if final_response else None,
            }

            logger.debug(f"LiteLLM response: response_id={result.get('response_id')}")
            return result

        except asyncio.CancelledError:
            # Must re-raise cancellation
            raise
        except Exception as e:
            logger.error(f"LiteLLM adapter error: {e}")
            raise RuntimeError(f"LiteLLM generation failed: {str(e)}") from e
