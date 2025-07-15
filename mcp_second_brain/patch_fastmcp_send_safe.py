"""Drop write-after-disconnect errors until FastMCP fixes #508/#823."""

import anyio
import logging
import os
from datetime import datetime
from mcp.server import session as _session  # FastMCP internals

logger = logging.getLogger(__name__)

# Debug file for tracking patch activity
DEBUG_FILE = os.path.join(os.getcwd(), "mcp_cancellation_debug.log")


def _debug_log(message: str):
    """Write debug message to file since user can't see stderr in interactive environment."""
    try:
        with open(DEBUG_FILE, "a") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write(f"[{timestamp}] PATCH: {message}\n")
            f.flush()
    except Exception:
        pass  # Silent fail if can't write


_debug_log("patch_fastmcp_send_safe module imported")

# Store the original method
if hasattr(_session.BaseSession, "_send_response"):
    _debug_log("BaseSession._send_response found - applying patch")
    _orig = _session.BaseSession._send_response  # keep original

    async def _send_response_safe(self, request_id, response):
        _debug_log(
            f"_send_response_safe called with request_id={request_id}, response type: {type(response).__name__}"
        )
        try:
            await _orig(self, request_id, response)  # normal path
        except (
            anyio.ClosedResourceError,  # client went away
            anyio.BrokenResourceError,
            anyio.EndOfStream,  # consumer closed stream during late flushes
        ) as e:
            _debug_log(f"Caught disconnect error: {type(e).__name__}: {e}")
            logger.debug("Client disconnected before response")

    # Patch once
    if getattr(_session, "_orig_send_response", None) is None:
        _session.BaseSession._send_response = _send_response_safe
        _session._orig_send_response = _orig
        logger.info("Successfully patched BaseSession._send_response")
        _debug_log("Successfully patched BaseSession._send_response")
    else:
        _debug_log("BaseSession._send_response already patched")
else:
    logger.warning("BaseSession._send_response not found - patch not applied")
    _debug_log("BaseSession._send_response not found - patch not applied")
