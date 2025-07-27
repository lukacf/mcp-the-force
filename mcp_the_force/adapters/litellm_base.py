"""Base adapter for LiteLLM-based adapters with shared functionality."""

import logging
from typing import Any, Dict, List, Optional
from abc import abstractmethod

import litellm
from litellm import aresponses

from .protocol import CallContext, ToolDispatcher
from .capabilities import AdapterCapabilities
from .errors import ToolExecutionException
from ..unified_session_cache import UnifiedSessionCache

logger = logging.getLogger(__name__)

# Configure LiteLLM globally
litellm.set_verbose = False
litellm.drop_params = True  # Drop unknown parameters


class LiteLLMBaseAdapter:
    """Base class for LiteLLM-based adapters.

    This provides common functionality for adapters that use LiteLLM's
    Responses API, including session management, tool handling, and
    response formatting.
    """

    # Protocol requirements - subclasses must set these
    model_name: str
    display_name: str
    capabilities: AdapterCapabilities
    param_class: type

    def __init__(self):
        """Initialize base adapter.

        Subclasses should call super().__init__() after setting their
        model_name, display_name, capabilities, and param_class.
        """
        self._validate_environment()

    @abstractmethod
    def _validate_environment(self):
        """Validate environment configuration.

        Subclasses must implement this to check for required API keys
        or environment variables.
        """
        pass

    @abstractmethod
    def _get_model_prefix(self) -> str:
        """Get the LiteLLM model prefix for this provider.

        Returns:
            The provider prefix (e.g., "vertex_ai", "xai")
        """
        pass

    def _convert_messages_to_input(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert chat format messages to Responses API input format.

        Args:
            messages: Messages in chat format

        Returns:
            Messages in Responses API input format
        """
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

    async def _load_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Load session history from cache.

        Args:
            session_id: Session identifier

        Returns:
            Conversation history in Responses API format
        """
        history = await UnifiedSessionCache.get_history(session_id)
        if history:
            logger.debug(
                f"[{self.display_name}] Loaded {len(history)} items from session {session_id}"
            )
            return history
        return []

    def _build_conversation_input(
        self,
        prompt: str,
        ctx: CallContext,
        messages: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        structured_output_schema: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build conversation input for the current turn.

        Args:
            prompt: User prompt
            ctx: Call context
            messages: Optional existing messages
            system_instruction: Optional system instruction
            structured_output_schema: Optional JSON schema

        Returns:
            Conversation input in Responses API format
        """
        conversation_input = []

        # Handle existing messages
        if messages:
            conversation_input.extend(self._convert_messages_to_input(messages))
        elif system_instruction:
            conversation_input.append(
                {
                    "type": "message",
                    "role": "system",
                    "content": [{"type": "text", "text": system_instruction}],
                }
            )

        # Add JSON formatting instruction if needed
        prompt_text = prompt
        if structured_output_schema and "json" not in prompt.lower():
            prompt_text = (
                f"{prompt}\n\nRespond ONLY with valid JSON that matches the schema."
            )

        # Add user message
        conversation_input.append(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": prompt_text}],
            }
        )

        return conversation_input

    def _get_tool_declarations(
        self,
        tool_dispatcher: Optional[ToolDispatcher],
        disable_memory_search: bool = False,
        additional_tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Get all tool declarations.

        Args:
            tool_dispatcher: Tool dispatcher instance
            disable_memory_search: Whether to disable memory search
            additional_tools: Additional tools to include

        Returns:
            List of tool declarations
        """
        tools = []

        if tool_dispatcher:
            built_in_tools = tool_dispatcher.get_tool_declarations(
                capabilities=self.capabilities,
                disable_memory_search=disable_memory_search,
            )
            tools.extend(built_in_tools)

        if additional_tools:
            tools.extend(additional_tools)

        return tools

    @abstractmethod
    def _build_request_params(
        self,
        conversation_input: List[Dict[str, Any]],
        params: Any,
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Build provider-specific request parameters.

        Args:
            conversation_input: Conversation in Responses API format
            params: Tool-specific parameters
            tools: Tool declarations
            **kwargs: Additional parameters

        Returns:
            Request parameters for LiteLLM
        """
        pass

    async def _handle_tool_calls(
        self,
        response: Any,
        tool_dispatcher: ToolDispatcher,
        conversation_input: List[Dict[str, Any]],
        request_params: Dict[str, Any],
        ctx: CallContext,
    ) -> tuple[Any, List[Dict[str, Any]]]:
        """Handle tool calls in the response.

        Args:
            response: LiteLLM response
            tool_dispatcher: Tool dispatcher
            conversation_input: Current conversation
            request_params: Request parameters

        Returns:
            Tuple of (final_response, updated_conversation)
        """
        final_response = response
        updated_conversation = list(conversation_input)

        # Handle tool calls in Responses API format
        while True:
            # Extract content and tool calls from response.output
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

            # If no tool calls, we're done
            if not tool_calls:
                break

            logger.debug(f"Processing {len(tool_calls)} tool calls")

            # Add assistant message to conversation
            updated_conversation.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": final_content or ""}],
                }
            )

            # Execute tool calls
            for tool_call in tool_calls:
                logger.debug(f"Executing tool: {tool_call.name}")
                try:
                    result = await tool_dispatcher.execute(
                        tool_name=tool_call.name,
                        tool_args=tool_call.arguments,
                        context=ctx,
                    )
                    updated_conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": str(result),
                        }
                    )
                except Exception as e:
                    tool_error = ToolExecutionException(
                        tool_name=tool_call.name, error=e, provider=self.display_name
                    )
                    logger.error(str(tool_error))
                    updated_conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": f"Error: {str(e)}",
                        }
                    )

            # Continue conversation with tool results
            request_params["input"] = updated_conversation
            response = await aresponses(**request_params)
            final_response = response

        return final_response, updated_conversation

    async def _save_session(
        self,
        ctx: CallContext,
        conversation_input: List[Dict[str, Any]],
        response: Any,
        updated_conversation: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Save session state.

        Args:
            ctx: Call context
            conversation_input: Original conversation
            response: Final response
            updated_conversation: Updated conversation with tool calls
        """
        if ctx.session_id:
            # Use updated conversation if available (includes tool calls)
            final_conversation = updated_conversation or conversation_input

            # Extract final content and add assistant response if not already included
            final_content = self._extract_content(response)
            if final_content and (
                not final_conversation
                or final_conversation[-1].get("role") != "assistant"
            ):
                assistant_msg = {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": final_content}],
                }
                final_conversation.append(assistant_msg)

            # Save to cache
            await UnifiedSessionCache.set_history(
                ctx.session_id,
                final_conversation,
            )

    def _extract_content(self, response: Any) -> str:
        """Extract content from LiteLLM Responses API response.

        Args:
            response: LiteLLM response object

        Returns:
            Extracted content string
        """
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
        params: Any,
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate response using LiteLLM.

        This is the main method that subclasses typically won't need to override.
        Instead, they should implement the abstract methods.

        Args:
            prompt: User prompt
            params: Tool-specific parameters
            ctx: Call context
            tool_dispatcher: Tool dispatcher
            **kwargs: Additional parameters

        Returns:
            Dict with "content" and other response data
        """
        try:
            # Load session history if needed
            conversation_input = []
            if ctx.session_id:
                conversation_input = await self._load_session_history(ctx.session_id)

            # Build conversation for current turn
            conversation_input.extend(
                self._build_conversation_input(
                    prompt,
                    ctx,
                    messages=kwargs.get("messages"),
                    system_instruction=kwargs.get("system_instruction"),
                    structured_output_schema=getattr(
                        params, "structured_output_schema", None
                    ),
                )
            )

            # Get tool declarations
            tools = self._get_tool_declarations(
                tool_dispatcher,
                disable_memory_search=getattr(params, "disable_memory_search", False),
                additional_tools=kwargs.get("tools"),
            )

            # Build provider-specific request parameters
            request_params = self._build_request_params(
                conversation_input, params, tools, **kwargs
            )

            # Make the API call
            response = await aresponses(**request_params)

            # Handle tool calls if present
            final_response, updated_conversation = await self._handle_tool_calls(
                response, tool_dispatcher, conversation_input, request_params, ctx
            )

            # Save session state
            await self._save_session(
                ctx, conversation_input, final_response, updated_conversation
            )

            # Extract and return content
            content = self._extract_content(final_response)
            result = {"content": content}

            # Add any provider-specific response data
            if hasattr(self, "_add_provider_specific_data"):
                result.update(self._add_provider_specific_data(final_response, params))

            return result

        except Exception as e:
            logger.error(f"[{self.display_name}] Error: {e}")
            raise
