"""
Patch MCP's request handler to properly handle CancelledError.
This prevents double responses when tools are cancelled via notifications/cancelled.
"""

import asyncio
import logging
import mcp.server.lowlevel.server
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

# Store the original _handle_request method
_original_handle_request = None

# Type variables from the original class
LifespanResultT = TypeVar("LifespanResultT")
RequestT = TypeVar("RequestT")


async def patched_handle_request(
    self,
    message,  # RequestResponder[types.ClientRequest, types.ServerResult]
    req: Any,
    session,  # ServerSession
    lifespan_context,  # LifespanResultT
    raise_exceptions: bool,
):
    """
    Patched version of _handle_request that properly handles CancelledError.
    When a tool is cancelled via notifications/cancelled, the RequestResponder
    has already sent an error response. We must not send another one.
    """
    logger.info("Processing request of type %s", type(req).__name__)
    
    # Import here to avoid circular imports
    import mcp.types as types
    from mcp.server.lowlevel.server import request_ctx, RequestContext, ServerMessageMetadata
    
    if handler := self.request_handlers.get(type(req)):  # type: ignore
        logger.debug("Dispatching request of type %s", type(req).__name__)

        token = None
        try:
            # Extract request context from message metadata
            request_data = None
            if message.message_metadata is not None and isinstance(message.message_metadata, ServerMessageMetadata):
                request_data = message.message_metadata.request_context

            # Set our global state that can be retrieved via
            # app.get_request_context()
            token = request_ctx.set(
                RequestContext(
                    message.request_id,
                    message.request_meta,
                    session,
                    lifespan_context,
                    request=request_data,
                )
            )
            response = await handler(req)
        except asyncio.CancelledError:
            # This occurs when a tool call is cancelled via notifications/cancelled.
            # The RequestResponder has already sent an error response.
            # We must not send another one. We just log and return.
            logger.info(f"Request {message.request_id} was cancelled. No further response will be sent.")
            return
        except types.McpError as err:
            response = err.error
        except Exception as err:
            if raise_exceptions:
                raise err
            response = types.ErrorData(code=0, message=str(err), data=None)
        finally:
            # Reset the global state after we are done
            if token is not None:
                request_ctx.reset(token)

        await message.respond(response)
    else:
        await message.respond(
            types.ErrorData(
                code=types.METHOD_NOT_FOUND,
                message="Method not found",
            )
        )

    logger.debug("Response sent")


def apply_patch():
    """Apply the patch to MCP's Server._handle_request method."""
    global _original_handle_request
    
    # Import the Server class
    Server = mcp.server.lowlevel.server.Server
    
    # Save the original method
    _original_handle_request = Server._handle_request
    
    # Replace with our patched version
    Server._handle_request = patched_handle_request
    
    logger.info("Applied cancellation handler patch to prevent double responses")


# Apply the patch when this module is imported
apply_patch()