"""
Swallow write-after-disconnect errors coming from notification sending.
Import *before* `from fastmcp import FastMCP`.
"""

import anyio
import logging
import os
import datetime
from mcp.shared.session import BaseSession

_LOG = logging.getLogger(__name__)


def _dbg(msg: str):
    try:
        with open(os.path.join(os.getcwd(), "mcp_cancellation_debug.log"), "a") as f:
            f.write(
                f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S.%f}] WRITER_PATCH: {msg}\n"
            )
    except Exception:
        pass


# Patch send_notification to handle disconnects gracefully
_orig_send_notification = BaseSession.send_notification


async def _safe_send_notification(self, *a, **kw):
    try:
        await _orig_send_notification(self, *a, **kw)
    except (
        anyio.BrokenResourceError,
        anyio.ClosedResourceError,
        anyio.EndOfStream,
        BrokenPipeError,
        ConnectionResetError,
        OSError,  # Include OSError for broken pipe
    ) as e:
        _LOG.debug("Client disconnected during notification send: %s", e)
        _dbg(f"Swallowed {type(e).__name__} in send_notification: {e}")  # keep a breadcrumb


BaseSession.send_notification = _safe_send_notification
_dbg("BaseSession.send_notification patched")
