"""
Centralized tool handling for built-in MCP tools across all adapters.

This module provides tool declaration and execution based on adapter capabilities.
"""

import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from .capabilities import AdapterCapabilities

logger = logging.getLogger(__name__)


class ToolHandler:
    """
    Centralizes the logic for declaring and executing built-in MCP tools.

    This class is stateless and thread-safe, designed to be called by
    adapters to eliminate code duplication in tool handling.

    Key design principles:
    - Stateless: No instance state that changes between calls
    - Async-safe: All methods are properly async
    - Extensible: Designed to evolve to Strategy pattern if needed
    - Error-preserving: Maintains existing error handling patterns
    """

    def __init__(self):
        """Initialize the tool handler. No state is stored."""
        pass

    async def execute_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        vector_store_ids: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Execute a single built-in tool call and return the result.

        This centralizes the duplicated execution logic from all adapters
        while preserving existing error handling patterns.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool
            vector_store_ids: Vector store IDs for attachment search
            session_id: Session ID for deduplication scope

        Returns:
            Tool execution result as string

        Raises:
            Exception: Re-raises exceptions from tool execution for proper
                      adapter-specific error categorization
        """
        # Establish the scope for the tool call
        from ..logging.setup import get_instance_id
        from ..utils.scope_manager import scope_manager

        scope_id = session_id or get_instance_id()
        if scope_id and not session_id:
            scope_id = f"instance_{scope_id}"

        async with scope_manager.scope(scope_id):
            try:
                if tool_name == "search_project_history":
                    return await self._execute_history_search(tool_args, session_id)
                elif tool_name == "search_task_files":
                    return await self._execute_task_files_search(
                        tool_args, vector_store_ids
                    )
                else:
                    logger.warning(f"Unknown built-in tool: {tool_name}")
                    return f"Error: Unknown tool '{tool_name}'"
            except Exception as e:
                # Re-raise exceptions to preserve adapter-specific error handling
                logger.error(f"Tool '{tool_name}' execution failed: {e}", exc_info=True)
                raise

    async def _execute_history_search(
        self, tool_args: Dict[str, Any], session_id: Optional[str] = None
    ) -> str:
        """Execute project history search tool."""
        from ..tools.search_history import HistorySearchService

        history_service = HistorySearchService()
        # Pass session_id for deduplication
        return await history_service.execute(session_id=session_id, **tool_args)

    async def _execute_task_files_search(
        self, tool_args: Dict[str, Any], vector_store_ids: Optional[List[str]]
    ) -> str:
        """Execute task files search tool."""
        from ..tools.search_task_files import SearchTaskFilesAdapter

        task_files_adapter = SearchTaskFilesAdapter()
        return await task_files_adapter.generate(
            prompt=tool_args.get("query", ""),
            vector_store_ids=vector_store_ids,
            **tool_args,
        )

    def prepare_tool_declarations(
        self,
        capabilities: AdapterCapabilities,
        vector_store_ids: Optional[List[str]] = None,
        disable_history_search: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Prepare tool declarations based on adapter capabilities.

        All tools are returned in OpenAI format since LiteLLM handles translation.

        Args:
            capabilities: Adapter capabilities
            vector_store_ids: Vector store IDs for attachment search
            disable_history_search: If True, skip search_project_history tool

        Returns:
            List of tool declarations in OpenAI format
        """
        declarations = []

        logger.info("[TOOL_HANDLER] prepare_tool_declarations called with:")
        logger.info(
            f"  - capabilities.native_vector_store_provider: {capabilities.native_vector_store_provider}"
        )
        logger.info(f"  - vector_store_ids: {vector_store_ids}")
        logger.info(f"  - disable_history_search: {disable_history_search}")

        # Only add tools if the adapter supports custom function calling tools
        if capabilities.supports_tools:
            # All adapters get the project history search tool unless disabled
            logger.debug(
                f"[TOOL_HANDLER] disable_history_search={disable_history_search}, not disable_history_search={not disable_history_search}"
            )
            if not disable_history_search:
                logger.debug("[TOOL_HANDLER] Adding search_project_history tool")
                declarations.append(self._get_history_declaration_openai())
            else:
                logger.debug(
                    "[TOOL_HANDLER] Skipping search_project_history tool (history search disabled)"
                )

            # Add task files search tool when vector stores are provided
            # Case 1: Non-native providers always get search_task_files
            # Case 2: OpenAI provider with non-OpenAI store IDs (HNSW fallback) also needs search_task_files
            should_add_search_task_files = False

            if vector_store_ids:
                if not capabilities.native_vector_store_provider:
                    # Non-native providers always need search_task_files
                    should_add_search_task_files = True
                    logger.info(
                        f"Adding search_task_files for non-native provider with {len(vector_store_ids)} stores"
                    )
                elif capabilities.native_vector_store_provider == "openai":
                    # Check if any store IDs are non-OpenAI (don't start with "vs_")
                    has_non_openai_stores = any(
                        not str(store_id).startswith("vs_")
                        for store_id in vector_store_ids
                    )
                    if has_non_openai_stores:
                        should_add_search_task_files = True
                        logger.info(
                            "[CHATTER FIX] OpenAI model with HNSW stores detected - adding search_task_files fallback"
                        )

            if should_add_search_task_files:
                declarations.append(self._get_task_files_declaration_openai())
            else:
                logger.debug("[TOOL_HANDLER] Not adding search_task_files because:")
                logger.debug(
                    f"  - vector_store_ids is {'empty' if not vector_store_ids else 'present'}"
                )
                logger.debug(
                    f"  - native_vector_store_provider is {capabilities.native_vector_store_provider}"
                )
                if (
                    vector_store_ids
                    and capabilities.native_vector_store_provider == "openai"
                ):
                    logger.debug("  - All store IDs are OpenAI native (vs_*)")
        else:
            logger.debug(
                "[TOOL_HANDLER] Skipping all custom tools because adapter doesn't support them"
            )

        logger.debug(f"[TOOL_HANDLER] Returning {len(declarations)} tool declarations")
        return declarations

    def _get_history_declaration_openai(self) -> Dict[str, Any]:
        """Get history search tool declaration in OpenAI format."""
        from .history_search_declaration import create_search_history_declaration_openai

        return create_search_history_declaration_openai()

    def _get_task_files_declaration_openai(self) -> Dict[str, Any]:
        """Get task files search tool declaration in OpenAI format."""
        from .task_files_search_declaration import (
            create_task_files_search_declaration_openai,
        )

        return create_task_files_search_declaration_openai()


# Future Strategy pattern interface (not implemented yet, but designed for migration)
class ToolStrategy(ABC):
    """
    Abstract strategy for tool handling.

    This interface is designed for future migration if we need more
    adapter-specific flexibility than the current ToolHandler provides.
    """

    @abstractmethod
    async def declare_tools(
        self, vector_store_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Declare available tools for this adapter type."""
        pass

    @abstractmethod
    async def execute_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        vector_store_ids: Optional[List[str]] = None,
    ) -> str:
        """Execute a tool call for this adapter type."""
        pass
