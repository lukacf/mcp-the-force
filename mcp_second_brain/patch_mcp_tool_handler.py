"""
Patch MCP lowlevel server to handle CancelledError gracefully.
This intercepts at the protocol handler level where tools are actually called.
Must be imported BEFORE any MCP server imports.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Callable, Awaitable
from mcp import types
from mcp.server.lowlevel.server import Server as MCPServer

logger = logging.getLogger(__name__)

# Debug file for tracking patch activity
DEBUG_FILE = os.path.join(os.getcwd(), "mcp_cancellation_debug.log")


def _debug_log(message: str):
    """Write debug message to file."""
    try:
        with open(DEBUG_FILE, "a") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write(f"[{timestamp}] PATCH_HANDLER: {message}\n")
            f.flush()
    except Exception:
        pass


_debug_log("patch_mcp_tool_handler module imported")

# Store the original method
_original_tool_decorator = MCPServer.tool


def patched_tool_decorator(
    self: MCPServer,
    *,
    validate_input: bool = False,
) -> Callable[
    [
        Callable[
            ...,
            Awaitable[
                types.UnstructuredContent
                | types.StructuredContent
                | types.CombinationContent
            ],
        ]
    ],
    Callable[
        ...,
        Awaitable[
            types.UnstructuredContent
            | types.StructuredContent
            | types.CombinationContent
        ],
    ],
]:
    """Patched tool decorator that wraps handlers to catch CancelledError."""
    _debug_log(f"patched_tool_decorator called with validate_input={validate_input}")

    # Get the original decorator
    original_decorator = _original_tool_decorator(self, validate_input=validate_input)

    def wrapper(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        # Apply the original decorator
        decorated_func = original_decorator(func)

        # Now we need to patch the actual handler that was registered
        # The original decorator registers a handler in request_handlers
        # We need to wrap that handler

        # Find the handler that was just registered (it's for CallToolRequest)
        if types.CallToolRequest in self.request_handlers:
            original_handler = self.request_handlers[types.CallToolRequest]

            async def safe_handler(req: types.CallToolRequest):
                """Wrapped handler that catches CancelledError."""
                _debug_log(f"safe_handler called for tool: {req.params.name}")
                try:
                    result = await original_handler(req)
                    _debug_log(f"Tool {req.params.name} completed successfully")
                    return result
                except asyncio.CancelledError:
                    _debug_log(
                        f"Tool {req.params.name} cancelled - returning error result"
                    )
                    logger.info(f"Tool '{req.params.name}' cancelled by user")
                    return self._make_error_result("Operation cancelled by user")
                except Exception as e:
                    _debug_log(f"Tool {req.params.name} raised {type(e).__name__}: {e}")
                    raise

            # Replace the handler
            self.request_handlers[types.CallToolRequest] = safe_handler
            _debug_log("Replaced CallToolRequest handler with safe version")

        return decorated_func

    return wrapper


# Replace the method
MCPServer.tool = patched_tool_decorator
_debug_log("Successfully patched MCPServer.tool decorator")
logger.info("Patched MCP lowlevel server tool decorator")
