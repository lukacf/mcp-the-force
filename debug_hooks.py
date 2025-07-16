#!/usr/bin/env python3
"""
Debugging hooks for MCP server cancellation investigation.
Import this at the top of server.py to enable debugging.
"""

import asyncio
import functools
import logging
import sys
import traceback

# Set up debug logging
debug_logger = logging.getLogger("mcp_debug")
debug_handler = logging.FileHandler("mcp_debug_trace.log")
debug_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s.%(msecs)03d - %(name)s - %(message)s", datefmt="%H:%M:%S"
    )
)
debug_logger.addHandler(debug_handler)
debug_logger.setLevel(logging.DEBUG)


def debug_log(msg):
    """Log to both file and console."""
    debug_logger.debug(msg)
    print(f"[DEBUG] {msg}", file=sys.stderr)


# Store original asyncio.Task methods
_original_task_cancel = asyncio.Task.cancel
_original_create_task = asyncio.create_task


def trace_task_cancel(self, msg=None):
    """Trace all task cancellations."""
    task_name = self.get_name() if hasattr(self, "get_name") else str(self)
    stack = traceback.extract_stack()

    debug_log(f"TASK CANCEL: {task_name}")
    debug_log(f"  Cancel message: {msg}")
    debug_log(
        f"  Called from: {stack[-2].filename}:{stack[-2].lineno} in {stack[-2].name}"
    )

    # Call original cancel
    return _original_task_cancel(self, msg)


def trace_create_task(coro, *, name=None, context=None):
    """Trace all task creations."""
    stack = traceback.extract_stack()
    caller = f"{stack[-2].filename}:{stack[-2].lineno} in {stack[-2].name}"

    task = _original_create_task(coro, name=name, context=context)

    debug_log(f"TASK CREATE: {task.get_name()}")
    debug_log(f"  Created by: {caller}")
    debug_log(f"  Coroutine: {coro}")

    return task


# Monkey-patch asyncio - commented out for Python 3.13 compatibility
# asyncio.Task.cancel = trace_task_cancel
asyncio.create_task = trace_create_task

# Also trace wait_for since it's commonly used
_original_wait_for = asyncio.wait_for


async def trace_wait_for(fut, timeout):
    """Trace asyncio.wait_for calls."""
    debug_log(f"WAIT_FOR: timeout={timeout}s")
    debug_log(f"  Future: {fut}")

    try:
        result = await _original_wait_for(fut, timeout)
        debug_log("WAIT_FOR completed successfully")
        return result
    except asyncio.TimeoutError:
        debug_log(f"WAIT_FOR timed out after {timeout}s")
        raise
    except asyncio.CancelledError:
        debug_log("WAIT_FOR was cancelled")
        raise


asyncio.wait_for = trace_wait_for


# Trace MCP message handling
def trace_mcp_handler(func):
    """Decorator to trace MCP handler functions."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        debug_log(f"MCP HANDLER: {func.__name__} called")
        debug_log(f"  Args: {args}")
        debug_log(f"  Kwargs: {kwargs}")

        try:
            result = await func(*args, **kwargs)
            debug_log(f"MCP HANDLER: {func.__name__} completed")
            return result
        except asyncio.CancelledError:
            debug_log(f"MCP HANDLER: {func.__name__} cancelled")
            raise
        except Exception as e:
            debug_log(f"MCP HANDLER: {func.__name__} error: {type(e).__name__}: {e}")
            raise

    return wrapper


import os

debug_log("=== MCP Debug Hooks Installed ===")
debug_log(f"Process PID: {os.getpid()}")
debug_log(f"Python version: {sys.version}")

# Export the decorator
__all__ = ["debug_log", "trace_mcp_handler"]
