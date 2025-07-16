"""
Simple patch to make all writes to stdout safe from disconnection errors.
"""

import logging
import functools
import anyio

_LOG = logging.getLogger(__name__)


def safe_write_decorator(original_func):
    """Decorator to make any write operation safe from disconnect errors."""

    @functools.wraps(original_func)
    async def wrapper(*args, **kwargs):
        try:
            return await original_func(*args, **kwargs)
        except (
            anyio.BrokenResourceError,
            anyio.ClosedResourceError,
            BrokenPipeError,
            ConnectionResetError,
            OSError,
        ) as e:
            _LOG.debug(f"Write failed (client disconnected): {type(e).__name__}")
            # Don't raise - pretend the write succeeded
            return None
        except Exception as e:
            # Check if it's a disconnect error by name
            error_name = type(e).__name__.lower()
            if any(x in error_name for x in ["broken", "closed", "pipe", "connection"]):
                _LOG.debug(f"Write failed (disconnect): {type(e).__name__}")
                return None
            # Other errors should propagate
            raise

    return wrapper


def patch_write_safety():
    """Apply safety patches to stdout write operations."""
    try:
        # Patch anyio file write operations if possible
        import anyio._core._files

        if hasattr(anyio._core._files.AsyncFile, "write"):
            original_write = anyio._core._files.AsyncFile.write
            anyio._core._files.AsyncFile.write = safe_write_decorator(original_write)
            _LOG.info("Patched anyio.AsyncFile.write for safe writes")
    except Exception as e:
        _LOG.debug(f"Could not patch anyio writes: {e}")

    # Also try to patch the MCP session send methods
    try:
        from mcp.shared.session import BaseSession

        if hasattr(BaseSession, "_write_message"):
            original = BaseSession._write_message
            BaseSession._write_message = safe_write_decorator(original)
            _LOG.info("Patched BaseSession._write_message for safe writes")
    except Exception as e:
        _LOG.debug(f"Could not patch BaseSession: {e}")


# Apply patches on import
patch_write_safety()
