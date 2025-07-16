"""
Patch the MCP RequestResponder to handle disconnections gracefully.

When a client disconnects (causing CancelledError), we should not try
to send responses as this will fail with write errors.
"""

import asyncio
import logging
import functools
from typing import Any

logger = logging.getLogger(__name__)


def patch_request_responder():
    """Patch RequestResponder.respond to handle client disconnections."""
    try:
        from mcp.shared.session import RequestResponder

        # Store the original respond method
        _original_respond = RequestResponder.respond

        @functools.wraps(_original_respond)
        async def respond_safe(self, response: Any) -> None:
            """
            Safe version of respond that handles disconnection errors.

            If the client has disconnected (causing write errors), we log
            and suppress the error instead of letting it propagate.
            """
            try:
                await _original_respond(self, response)
            except (
                BrokenPipeError,
                ConnectionResetError,
                asyncio.CancelledError,
                OSError,
            ) as e:
                # Client disconnected - log and suppress
                logger.info(
                    f"Cannot send response - client disconnected: {type(e).__name__}"
                )
                # Don't re-raise - let the request complete cleanly
            except Exception as e:
                # Check for other disconnect-related errors by name
                error_name = type(e).__name__.lower()
                if any(
                    x in error_name
                    for x in ["broken", "closed", "pipe", "connection", "cancelled"]
                ):
                    logger.info(
                        f"Cannot send response - client disconnected: {type(e).__name__}"
                    )
                    return
                # Other errors should propagate
                raise

        # Replace the method
        RequestResponder.respond = respond_safe
        logger.info(
            "Successfully patched RequestResponder.respond for disconnect handling"
        )

    except Exception as e:
        logger.error(f"Failed to patch RequestResponder: {e}")


def patch_request_responder_cancel():
    """Patch RequestResponder.cancel to prevent double responses."""
    try:
        from mcp.shared.session import RequestResponder

        # Store the original cancel method
        _original_cancel = RequestResponder.cancel

        @functools.wraps(_original_cancel)
        async def cancel_no_double_response(self) -> None:
            """
            Cancel that doesn't send response if already completed.

            Claude Code sends a delayed notifications/cancelled message ~60s
            after the user aborts. By then, we've already sent a response.
            This patch prevents the double response error.
            """
            # If we've already sent a response, don't send another
            if hasattr(self, "_completed") and self._completed:
                logger.info("Responder already completed, skipping cancel response")
                # Still cancel the scope but don't send a response
                if hasattr(self, "_cancel_scope"):
                    self._cancel_scope.cancel()
                return

            # Otherwise proceed with normal cancellation
            await _original_cancel(self)

        # Replace the method
        RequestResponder.cancel = cancel_no_double_response
        logger.info(
            "Successfully patched RequestResponder.cancel to prevent double responses"
        )

    except Exception as e:
        logger.error(f"Failed to patch RequestResponder.cancel: {e}")


# Apply patches on import
patch_request_responder()
patch_request_responder_cancel()
