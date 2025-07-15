"""
Patch FastMCP to handle CancelledError properly during tool execution.

This patch ensures that when a tool execution is cancelled (e.g., when Claude
aborts a request), we don't try to send a response after cancellation.
"""

import asyncio
import logging
from typing import Any, List, Tuple, Union

logger = logging.getLogger(__name__)


def patch_fastmcp():
    """Apply the patch to FastMCP's _mcp_call_tool method."""
    try:
        # Import FastMCP and MCP types
        from fastmcp import FastMCP
        from mcp.types import ContentBlock
        
        # Store the original method
        _original_mcp_call_tool = FastMCP._mcp_call_tool
        
        async def _mcp_call_tool_safe(
            self, key: str, arguments: dict[str, Any]
        ) -> Union[List[ContentBlock], Tuple[List[ContentBlock], dict[str, Any]]]:
            """
            Wrapper for _mcp_call_tool that handles CancelledError properly.
            
            When a request is cancelled (e.g., Claude aborts), we should not
            try to send a response because:
            1. The client has already disconnected
            2. The MCP protocol handler will have already sent a cancellation response
            3. Trying to send another response will cause errors
            """
            try:
                # Call the original method
                return await _original_mcp_call_tool(self, key, arguments)
            except asyncio.CancelledError:
                # Log that we caught the cancellation
                logger.info(f"Tool '{key}' execution was cancelled - suppressing response")
                # Re-raise to let the cancellation propagate properly
                # The MCP server will handle this and NOT try to send a response
                raise
            except Exception:
                # Let all other exceptions propagate normally
                raise
        
        # Replace the method
        FastMCP._mcp_call_tool = _mcp_call_tool_safe
        logger.info("Successfully patched FastMCP._mcp_call_tool for proper cancellation handling")
        
    except Exception as e:
        logger.error(f"Failed to patch FastMCP: {e}")


# Apply the patch when this module is imported
patch_fastmcp()