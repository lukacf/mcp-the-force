"""Bridge adapter for Gemini to connect protocol-based adapter to legacy system."""

import logging
from typing import Any, Dict, List, Optional, Union, cast
from types import SimpleNamespace

from .base import BaseAdapter
from .gemini_new import GeminiAdapter
from .tool_dispatcher import ToolDispatcher
from .protocol import CallContext
from .params import GeminiToolParams

logger = logging.getLogger(__name__)


class GeminiBridgeAdapter(BaseAdapter):
    """Bridge adapter connecting protocol-based GeminiAdapter to legacy system.

    This is temporary scaffolding that allows the new protocol-based Gemini
    adapter to work with the existing framework that expects BaseAdapter.
    """

    def __init__(self, model_name: str = "gemini-2.5-pro"):
        """Initialize the bridge with a protocol-based adapter.

        Args:
            model_name: The Gemini model to use
        """
        # Create the protocol-based adapter
        self.protocol_adapter = GeminiAdapter(model_name)

        # Copy attributes for BaseAdapter compatibility
        self.model_name = self.protocol_adapter.model_name
        self.display_name = self.protocol_adapter.display_name

        # Set context window from capabilities
        self.context_window = (
            self.protocol_adapter.capabilities.max_context_window or 1_000_000
        )

        logger.info(
            f"[GEMINI_BRIDGE] Initialized bridge for {model_name} "
            f"with {self.context_window:,} token context"
        )

    async def generate(
        self,
        prompt: str,
        vector_store_ids: Optional[List[str]] = None,
        max_reasoning_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        temperature: Optional[float] = None,
        return_debug: bool = False,
        messages: Optional[List[Dict[str, str]]] = None,
        system_instruction: Optional[str] = None,
        structured_output_schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Union[str, Dict[str, Any]]:
        """Generate response, translating from legacy to protocol interface.

        This method translates the legacy BaseAdapter interface to the new
        protocol-based interface.
        """
        logger.info(
            f"[GEMINI_BRIDGE] Generating response for session: {kwargs.get('session_id')}"
        )

        # Extract session_id from kwargs
        session_id = kwargs.get("session_id")

        # Extract other parameters that might be in kwargs
        disable_memory_search = kwargs.get("disable_memory_search", False)
        tools = kwargs.get("tools", [])
        tool_choice = kwargs.get("tool_choice", "auto")

        # Create parameter object with all the settings using cast pattern
        params: GeminiToolParams = cast(
            GeminiToolParams,
            SimpleNamespace(
                instructions=prompt,
                output_format="",  # Not used in legacy interface
                context=[],  # Not used in legacy interface
                session_id=session_id or "",
                # Gemini-specific parameters
                temperature=temperature if temperature is not None else 1.0,
                reasoning_effort=reasoning_effort,
                disable_memory_search=disable_memory_search,
                structured_output_schema=structured_output_schema,
            ),
        )

        # Create call context
        ctx = CallContext(
            session_id=session_id or "",
            vector_store_ids=vector_store_ids,
        )

        # Create tool dispatcher with vector store IDs
        tool_dispatcher = ToolDispatcher(vector_store_ids=vector_store_ids)

        # Prepare kwargs for protocol adapter
        protocol_kwargs = {
            "tools": tools,
            "tool_choice": tool_choice,
            "system_instruction": system_instruction,
            "messages": messages,  # Pass through for compatibility
            "max_reasoning_tokens": max_reasoning_tokens,  # Pass through
        }

        # Remove None values
        protocol_kwargs = {k: v for k, v in protocol_kwargs.items() if v is not None}

        try:
            # Call the protocol-based adapter
            result = await self.protocol_adapter.generate(
                prompt=prompt,
                params=params,
                ctx=ctx,
                tool_dispatcher=tool_dispatcher,
                **protocol_kwargs,
            )

            # Extract content from result
            content: str = result.get("content", "")

            # Return debug format if requested
            if return_debug:
                return {
                    "content": content,
                    "_debug_tools": tool_dispatcher.get_tool_declarations(
                        adapter_type="gemini",
                        disable_memory_search=disable_memory_search,
                    ),
                }

            return content

        except Exception as e:
            logger.error(
                f"[GEMINI_BRIDGE] Error in generate: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            raise
