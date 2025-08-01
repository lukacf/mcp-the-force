"""Tool dispatcher implementation for protocol-based adapters."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from .tool_handler import ToolHandler
from .protocol import CallContext, ToolCall
from .capabilities import AdapterCapabilities

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
        self, capabilities: AdapterCapabilities, disable_history_search: bool = False
    ) -> List[Dict[str, Any]]:
        """Get tool declarations in the format expected by the adapter.

        Args:
            capabilities: Adapter capabilities
            disable_history_search: Whether to disable search_project_history tool

        Returns:
            List of tool declarations in the appropriate format
        """
        return self.tool_handler.prepare_tool_declarations(
            capabilities=capabilities,
            vector_store_ids=self.vector_store_ids,
            disable_history_search=disable_history_search,
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

    async def execute_batch(
        self, tool_calls: List[ToolCall], context: CallContext
    ) -> List[str]:
        """Execute multiple tools in parallel and return their results.

        Args:
            tool_calls: List of tool calls to execute
            context: Call context

        Returns:
            List of string results, one per tool call
        """

        async def execute_single(tool_call: ToolCall) -> str:
            """Execute a single tool call and return the result as a string."""
            try:
                # Update context with tool_call_id if provided
                call_context = CallContext(
                    session_id=context.session_id,
                    project=context.project,
                    tool=context.tool,
                    vector_store_ids=context.vector_store_ids,
                    tool_call_id=tool_call.tool_call_id,
                )

                result = await self.execute(
                    tool_name=tool_call.tool_name,
                    tool_args=tool_call.tool_args,
                    context=call_context,
                )

                # Convert result to string if needed
                if isinstance(result, str):
                    return result
                else:
                    return json.dumps(result, ensure_ascii=False)

            except Exception as e:
                logger.error(f"Tool execution failed for {tool_call.tool_name}: {e}")
                return f"Error executing {tool_call.tool_name}: {str(e)}"

        # Execute all tools in parallel
        tasks = [execute_single(tool_call) for tool_call in tool_calls]
        results = await asyncio.gather(*tasks)

        return results
