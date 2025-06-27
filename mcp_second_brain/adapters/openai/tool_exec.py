"""Bounded tool executor for OpenAI adapter."""

import asyncio
import json
import logging
from typing import List, Dict, Any, Callable, Optional
from .constants import GLOBAL_TOOL_LIMITER
from .errors import AdapterException, ErrorCategory, ToolExecutionException

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes tool calls with controlled parallelism using a global semaphore."""

    def __init__(self, tool_dispatcher: Callable[[str, Any], Any]):
        """Initialize with a tool dispatcher function.

        Args:
            tool_dispatcher: Async function that takes (tool_name, arguments)
                           and returns the tool result.
        """
        self._dispatch = tool_dispatcher

    async def run_all(self, tool_calls: List[Any]) -> List[Dict[str, Any]]:
        """Executes all tool calls with controlled parallelism.

        Args:
            tool_calls: List of tool call objects from OpenAI response.
                       Each should have 'name', 'call_id', and 'arguments'.

        Returns:
            List of results in the same order as tool_calls.
            Each result is a dict with 'call_id' and 'output'.
        """
        if not tool_calls:
            return []

        results: List[Optional[Dict[str, Any]]] = [None] * len(tool_calls)

        # For Python 3.10 compatibility, use gather instead of TaskGroup
        tasks = [
            self._execute_one_with_limit(call, results, i)
            for i, call in enumerate(tool_calls)
        ]

        # Execute all tasks concurrently
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            # Convert any exception to AdapterException
            if isinstance(e, ToolExecutionException):
                error_msg = str(e)
            else:
                error_msg = f"Unexpected error: {e}"

            raise AdapterException(
                ErrorCategory.TOOL_EXECUTION,
                f"Tool execution failed: {error_msg}",
            )

        # All results should be populated now - filter out None values
        return [r for r in results if r is not None]

    async def _execute_one_with_limit(
        self, call: Any, results: List[Optional[Dict[str, Any]]], index: int
    ):
        """Execute a single tool call with semaphore limiting."""
        async with GLOBAL_TOOL_LIMITER:
            await self._execute_one(call, results, index)

    async def _execute_one(
        self, call: Any, results: List[Optional[Dict[str, Any]]], index: int
    ):
        """Executes a single tool and places the result in the shared list.

        This method captures errors but does not raise them, allowing other
        tools to complete. Errors are returned as part of the result.
        """
        # Extract call details - handle both dict and object representations
        if isinstance(call, dict):
            call_id = call.get("call_id")
            name = call.get("name")
            arguments = call.get("arguments", "{}")
        else:
            # Handle object-like tool calls (e.g., ResponseFunctionToolCall)
            call_id = getattr(call, "call_id", None)
            name = getattr(call, "name", None)
            arguments = getattr(call, "arguments", "{}")

        logger.info(f"Executing tool '{name}' (call_id: {call_id})")

        try:
            # Parse arguments
            if isinstance(arguments, str):
                try:
                    parsed_args = json.loads(arguments)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse arguments for {name}: {e}")
                    parsed_args = {}
            else:
                parsed_args = arguments

            # Execute the tool
            tool_output = await self._dispatch(name or "", parsed_args)

            # Format successful result
            results[index] = {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(tool_output)
                if not isinstance(tool_output, str)
                else tool_output,
            }

            logger.info(f"Tool '{name}' completed successfully")

        except Exception as e:
            # Capture the error but do not raise it
            error_message = f"Tool '{name}' failed: {str(e)}"
            logger.error(error_message, exc_info=True)

            # Return error as result to allow other tools to complete
            results[index] = {
                "type": "function_call_output",
                "call_id": call_id,
                "output": error_message,
            }


class BuiltInToolDispatcher:
    """Handles execution of OpenAI's built-in tools (search_memory, search_attachments)."""

    def __init__(self, vector_store_ids: Optional[List[str]] = None):
        """Initialize with optional vector store IDs for attachment search.

        Args:
            vector_store_ids: List of vector store IDs for attachment search.
        """
        self.vector_store_ids = vector_store_ids

    async def dispatch(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Dispatch to the appropriate built-in tool.

        Args:
            name: Tool name (e.g., "search_project_memory", "search_session_attachments")
            arguments: Parsed arguments for the tool

        Returns:
            Tool execution result
        """
        if name == "search_project_memory":
            # Import and execute search
            from ...tools.search_memory import SearchMemoryAdapter

            adapter = SearchMemoryAdapter()
            return await adapter.generate(
                prompt=arguments.get("query", ""),
                query=arguments.get("query", ""),
                max_results=arguments.get("max_results", 40),
                store_types=arguments.get("store_types", ["conversation", "commit"]),
            )

        elif name == "search_session_attachments":
            # Import and execute attachment search
            from ...tools.search_attachments import SearchAttachmentAdapter

            adapter_attachment = SearchAttachmentAdapter()
            return await adapter_attachment.generate(
                prompt=arguments.get("query", ""),
                query=arguments.get("query", ""),
                max_results=arguments.get("max_results", 20),
                vector_store_ids=self.vector_store_ids,
            )
        else:
            raise ValueError(f"Unknown built-in tool: {name}")
