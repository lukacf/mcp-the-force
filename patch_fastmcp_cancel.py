"""
Patch FastMCP to handle CancelledError without sending a response.
This prevents the "Request already responded to" error.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

def patch_fastmcp_cancel():
    """Patch FastMCP to handle CancelledError gracefully."""
    try:
        import fastmcp
        from fastmcp.exceptions import ToolError
        
        # Find the FastMCP class
        if hasattr(fastmcp, 'FastMCP'):
            FastMCPClass = fastmcp.FastMCP
        else:
            # Try to find it in submodules
            for attr_name in dir(fastmcp):
                attr = getattr(fastmcp, attr_name)
                if hasattr(attr, 'FastMCP'):
                    FastMCPClass = attr.FastMCP
                    break
            else:
                logger.warning("Could not find FastMCP class to patch")
                return
        
        # Find and patch the tool execution method
        for method_name in ['_handle_tool_call', 'handle_tool_call', '_execute_tool', 'execute_tool', 'call_tool']:
            if hasattr(FastMCPClass, method_name):
                original_method = getattr(FastMCPClass, method_name)
                
                async def patched_method(self, *args, **kwargs):
                    """Handle CancelledError without sending a response."""
                    try:
                        return await original_method(self, *args, **kwargs)
                    except asyncio.CancelledError:
                        # Log but don't send any response
                        logger.info("Tool cancelled - suppressing FastMCP response")
                        # Return None to indicate no response should be sent
                        return None
                    except Exception:
                        # Let other exceptions through normally
                        raise
                
                setattr(FastMCPClass, method_name, patched_method)
                logger.info(f"Patched FastMCP.{method_name} to suppress cancellation responses")
                break
        
    except Exception as e:
        logger.warning(f"Failed to patch FastMCP: {e}")

# Apply patch when imported
patch_fastmcp_cancel()