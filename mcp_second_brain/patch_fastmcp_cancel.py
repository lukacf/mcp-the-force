"""
Convert CancelledError → ToolError so FastMCP treats user aborts
as normal tool failures instead of fatal server errors.
Must be imported *before* `from fastmcp import FastMCP`.
"""

import asyncio
import logging
import os
from datetime import datetime
from fastmcp import FastMCP
import fastmcp.exceptions

logger = logging.getLogger(__name__)

# Debug file for tracking patch activity
DEBUG_FILE = os.path.join(os.getcwd(), "mcp_cancellation_debug.log")


def _debug_log(message: str):
    """Write debug message to file."""
    try:
        with open(DEBUG_FILE, "a") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write(f"[{timestamp}] PATCH_CANCEL: {message}\n")
            f.flush()
    except Exception:
        pass


_debug_log("patch_fastmcp_cancel module imported")

# Patch the CORRECT method: _mcp_call_tool (with underscore)
_orig = FastMCP._mcp_call_tool
_debug_log(f"Original _mcp_call_tool: {_orig}")


async def _safe(self: FastMCP, key: str, args: dict):
    """Convert CancelledError to ToolError at the protocol handler level."""
    _debug_log(f"_mcp_call_tool wrapper called for tool: {key}")
    try:
        result = await _orig(self, key, args)
        _debug_log(f"Tool {key} completed successfully")
        return result
    except asyncio.CancelledError:
        _debug_log(f"Tool '{key}' cancelled - converting to ToolError")
        logger.info(f"Tool '{key}' cancelled by user")
        raise fastmcp.exceptions.ToolError("Operation cancelled by user") from None
    except Exception as e:
        _debug_log(f"Tool {key} raised {type(e).__name__}: {e}")
        raise


FastMCP._mcp_call_tool = _safe
_debug_log("Successfully patched FastMCP._mcp_call_tool")

logger.info("Patched FastMCP._mcp_call_tool to handle cancellations gracefully")
