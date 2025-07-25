"""Tool dispatcher implementation for protocol-based adapters."""

import json
import logging
from typing import Any, Dict, List, Optional
from .tool_handler import ToolHandler
from .protocol import CallContext

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """Concrete implementation of the ToolDispatcher protocol.

    This wraps the existing ToolHandler to provide the protocol interface
    expected by new adapters.
    """

    def __init__(self, vector_store_ids: Optional[List[str]] = None):
        """Initialize with tool handler."""
        self.tool_handler = ToolHandler()
        self.vector_store_ids = vector_store_ids or []

    def get_tool_declarations(
        self, adapter_type: str = "openai", disable_memory_search: bool = False
    ) -> List[Dict[str, Any]]:
        """Get tool declarations in the format expected by the adapter.

        Args:
            adapter_type: Type of adapter ("openai", "grok", "gemini")
            disable_memory_search: Whether to disable search_project_history tool

        Returns:
            List of tool declarations in the appropriate format
        """
        # Use the existing tool handler's method
        return self.tool_handler.prepare_tool_declarations(
            adapter_type=adapter_type,  # type: ignore[arg-type]
            vector_store_ids=self.vector_store_ids,
            disable_memory_search=disable_memory_search,
        )

    async def execute(
        self, tool_name: str, tool_args: str, context: CallContext
    ) -> Any:
        """Execute a tool and return its result.

        Args:
            tool_name: Name of the tool to execute
            tool_args: JSON string of tool arguments
            context: Call context

        Returns:
            Tool execution result
        """
        # Parse arguments if they're a string
        if isinstance(tool_args, str):
            try:
                args_dict = json.loads(tool_args)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool args: {e}")
                return "Error: Invalid tool arguments format"
        else:
            args_dict = tool_args

        # Execute using the tool handler
        try:
            result = await self.tool_handler.execute_tool_call(
                tool_name=tool_name,
                tool_args=args_dict,
                vector_store_ids=context.vector_store_ids,
                session_id=context.session_id,
            )
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return f"Error executing {tool_name}: {str(e)}"
