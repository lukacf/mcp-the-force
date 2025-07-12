"""
Centralized tool handling for built-in MCP tools across all adapters.

This module implements a DRY solution for tool declaration and execution
that was previously duplicated across OpenAI, Vertex, and Grok adapters.
"""

import logging
from typing import List, Dict, Any, Optional, Literal
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Type alias for supported adapter types
AdapterType = Literal["openai", "vertex", "grok"]


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
    ) -> str:
        """
        Execute a single built-in tool call and return the result.

        This centralizes the duplicated execution logic from all adapters
        while preserving existing error handling patterns.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool
            vector_store_ids: Vector store IDs for attachment search

        Returns:
            Tool execution result as string

        Raises:
            Exception: Re-raises exceptions from tool execution for proper
                      adapter-specific error categorization
        """
        try:
            if tool_name == "search_project_memory":
                return await self._execute_memory_search(tool_args)
            elif tool_name == "search_session_attachments":
                return await self._execute_attachment_search(
                    tool_args, vector_store_ids
                )
            else:
                logger.warning(f"Unknown built-in tool: {tool_name}")
                return f"Error: Unknown tool '{tool_name}'"
        except Exception as e:
            # Re-raise exceptions to preserve adapter-specific error handling
            logger.error(f"Tool '{tool_name}' execution failed: {e}", exc_info=True)
            raise

    async def _execute_memory_search(self, tool_args: Dict[str, Any]) -> str:
        """Execute project memory search tool."""
        from ..tools.search_memory import SearchMemoryAdapter

        memory_adapter = SearchMemoryAdapter()
        return await memory_adapter.generate(
            prompt=tool_args.get("query", ""), **tool_args
        )

    async def _execute_attachment_search(
        self, tool_args: Dict[str, Any], vector_store_ids: Optional[List[str]]
    ) -> str:
        """Execute session attachment search tool."""
        from ..tools.search_attachments import SearchAttachmentAdapter

        attachment_adapter = SearchAttachmentAdapter()
        return await attachment_adapter.generate(
            prompt=tool_args.get("query", ""),
            vector_store_ids=vector_store_ids,
            **tool_args,
        )

    def prepare_tool_declarations(
        self,
        adapter_type: AdapterType,
        vector_store_ids: Optional[List[str]] = None,
        disable_memory_search: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Prepare tool declarations in the correct format for the adapter type.

        This centralizes the logic for determining which tools to declare
        and formats them correctly for each adapter's API requirements.

        Args:
            adapter_type: Type of adapter (openai, vertex, grok)
            vector_store_ids: Vector store IDs that determine if attachment
                            search tool should be included
            disable_memory_search: If True, skip declaring search_project_memory tool

        Returns:
            List of tool declarations in the correct format for the adapter

        Raises:
            ValueError: If adapter_type is not supported
        """
        if adapter_type not in {"openai", "vertex", "grok"}:
            raise ValueError(f"Unsupported adapter type: {adapter_type}")

        declarations = []

        # All adapters get the project memory search tool unless disabled
        if not disable_memory_search:
            if adapter_type in {"openai", "grok"}:
                declarations.append(self._get_memory_declaration_openai())
            elif adapter_type == "vertex":
                declarations.append(self._get_memory_declaration_vertex())

        # Add attachment search tool when vector stores are provided
        if vector_store_ids:
            logger.info(
                f"Adding attachment search tool for {adapter_type} adapter "
                f"with {len(vector_store_ids)} vector stores"
            )
            if adapter_type in {"openai", "grok"}:
                declarations.append(self._get_attachment_declaration_openai())
            elif adapter_type == "vertex":
                declarations.append(self._get_attachment_declaration_vertex())

        return declarations

    def _get_memory_declaration_openai(self) -> Dict[str, Any]:
        """Get memory search tool declaration for OpenAI-compatible APIs."""
        from .memory_search_declaration import create_search_memory_declaration_openai

        return create_search_memory_declaration_openai()

    def _get_memory_declaration_vertex(self) -> Dict[str, Any]:
        """Get memory search tool declaration for Vertex AI."""
        from .memory_search_declaration import create_search_memory_declaration_gemini

        return create_search_memory_declaration_gemini()

    def _get_attachment_declaration_openai(self) -> Dict[str, Any]:
        """Get attachment search tool declaration for OpenAI-compatible APIs."""
        from .attachment_search_declaration import (
            create_attachment_search_declaration_openai,
        )

        return create_attachment_search_declaration_openai()

    def _get_attachment_declaration_vertex(self) -> Dict[str, Any]:
        """Get attachment search tool declaration for Vertex AI."""
        from .attachment_search_declaration import (
            create_attachment_search_declaration_gemini,
        )

        return create_attachment_search_declaration_gemini()


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
