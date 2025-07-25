"""Bridge adapter connecting protocol-based OpenAI adapter to legacy system.

This is temporary scaffolding that will be removed once the framework
is updated to work directly with protocol adapters.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from types import SimpleNamespace
from typing import cast

from .base import BaseAdapter
from .openai_new.adapter import OpenAIProtocolAdapter
from .protocol import CallContext
from .tool_handler import ToolHandler

logger = logging.getLogger(__name__)


class OpenAIBridgeAdapter(BaseAdapter):
    """Bridge adapter for protocol-based OpenAI adapter.

    This adapter provides backward compatibility by implementing the
    legacy BaseAdapter interface while delegating to the new
    protocol-based OpenAI adapter.
    """

    def __init__(self, model_name: str = "o3"):
        """Initialize bridge adapter.

        Args:
            model_name: OpenAI model name
        """
        # Create the protocol-based adapter
        self.protocol_adapter = OpenAIProtocolAdapter(model_name)

        # Copy attributes for BaseAdapter compatibility
        self.model_name = self.protocol_adapter.model_name
        self.display_name = self.protocol_adapter.display_name

        # Set context window from capabilities
        self.context_window = (
            self.protocol_adapter.capabilities.max_context_window or 200_000
        )

        # Set description snippet
        self.description_snippet = (
            f"{self.protocol_adapter.display_name}: "
            f"{self.protocol_adapter.capabilities.description}"
        )

    async def generate(
        self,
        prompt: str,
        vector_store_ids: Optional[List[str]] = None,
        **kwargs,
    ) -> Union[str, Dict[str, Any]]:
        """Generate response using protocol adapter.

        This method translates the legacy generate signature to the
        protocol-based generate signature.
        """
        # Extract parameters that map to protocol adapter
        session_id = kwargs.get("session_id")
        reasoning_effort = kwargs.get("reasoning_effort")
        structured_output_schema = kwargs.get("structured_output_schema")
        disable_memory_search = kwargs.get("disable_memory_search", False)

        # Create params object (using SimpleNamespace as lightweight container)
        params = SimpleNamespace(
            instructions=prompt,
            output_format="",  # Not used by OpenAI adapter
            context=[],  # Not used by OpenAI adapter
            session_id=session_id or "",
            reasoning_effort=reasoning_effort,
            disable_memory_search=disable_memory_search,
            structured_output_schema=structured_output_schema,
        )

        # Create call context
        ctx = CallContext(
            session_id=session_id or "",
            vector_store_ids=vector_store_ids,
        )

        # Create tool dispatcher wrapper for ToolHandler
        tool_handler = ToolHandler()

        # Create a simple wrapper that adapts ToolHandler to ToolDispatcher protocol
        class ToolDispatcherWrapper:
            def __init__(self, handler: ToolHandler):
                self.handler = handler

            def get_tool_declarations(
                self, adapter_type: str, disable_memory_search: bool = False
            ):
                # ToolHandler doesn't have this method, so we return empty list
                # The OpenAI flow.py will add its own tools
                return []

            async def execute(
                self, tool_name: str, tool_args: str, context: CallContext
            ):
                # Convert string args to dict and call ToolHandler
                import json

                args_dict = json.loads(tool_args) if tool_args else {}
                return await self.handler.execute_tool_call(
                    tool_name=tool_name,
                    tool_args=args_dict,
                    vector_store_ids=context.vector_store_ids,
                    session_id=context.session_id,
                )

        tool_dispatcher = ToolDispatcherWrapper(tool_handler)

        # Call protocol adapter
        # Cast params to satisfy mypy - the protocol adapter will handle validation
        from ..params import OpenAIToolParams

        result = await self.protocol_adapter.generate(
            prompt=prompt,
            params=cast(OpenAIToolParams, params),
            ctx=ctx,
            tool_dispatcher=tool_dispatcher,
            **kwargs,  # Pass through remaining kwargs
        )

        # Return result (already in expected format)
        return result
