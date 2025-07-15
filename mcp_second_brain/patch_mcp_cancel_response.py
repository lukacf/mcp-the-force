"""
Patch MCP RequestResponder to prevent automatic error response on cancellation.
This allows our tool handlers to send their own error responses.
Must be imported BEFORE any MCP imports.
"""

import logging
import os
from datetime import datetime
from mcp.shared.session import RequestResponder

logger = logging.getLogger(__name__)

# Debug file for tracking patch activity
DEBUG_FILE = os.path.join(os.getcwd(), "mcp_cancellation_debug.log")


def _debug_log(message: str):
    """Write debug message to file."""
    try:
        with open(DEBUG_FILE, "a") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write(f"[{timestamp}] PATCH_CANCEL_RESP: {message}\n")
            f.flush()
    except Exception:
        pass


_debug_log("patch_mcp_cancel_response module imported")

# Store the original cancel method
_original_cancel = RequestResponder.cancel


async def patched_cancel(self):
    """Cancel this request without sending an automatic error response."""
    _debug_log(f"patched_cancel called for request_id={self.request_id}")

    if not self._entered:
        raise RuntimeError("RequestResponder must be used as a context manager")
    if not self._cancel_scope:
        raise RuntimeError("No active cancel scope")

    # Cancel the scope
    self._cancel_scope.cancel()

    # Mark as completed WITHOUT sending an error response
    # This allows the tool handler to send its own response
    self._completed = True
    _debug_log(f"Cancelled request {self.request_id} without sending error response")


# Replace the method
RequestResponder.cancel = patched_cancel
_debug_log("Successfully patched RequestResponder.cancel")
logger.info("Patched RequestResponder.cancel to prevent automatic error responses")
