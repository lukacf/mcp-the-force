#!/usr/bin/env python3
"""
Enhanced cancellation tracer that hooks into the MCP server to trace all cancellation events.
This will show us exactly what happens when Claude Code aborts.
"""

import sys
import os
import time
import asyncio
import traceback
from datetime import datetime
from typing import Any, Coroutine

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Global trace file
TRACE_FILE = "cancellation_trace.log"


def trace_log(msg: str, level: str = "INFO"):
    """Write to trace file with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with open(TRACE_FILE, "a") as f:
        f.write(f"[{timestamp}] [{level}] {msg}\n")
        f.flush()


# Clear trace file
with open(TRACE_FILE, "w") as f:
    f.write(f"=== Cancellation Trace Started at {datetime.now()} ===\n")

trace_log("Starting cancellation tracer...")

# Monkey-patch asyncio.Task to trace all cancellations
original_task_cancel = asyncio.Task.cancel


def traced_cancel(self, msg=None):
    """Traced version of Task.cancel()"""
    task_name = self.get_name()
    coro_name = (
        self.get_coro().__name__
        if hasattr(self.get_coro(), "__name__")
        else str(self.get_coro())
    )

    # Get stack trace of who's calling cancel
    stack = traceback.extract_stack()
    caller_info = []
    for frame in stack[-10:-1]:  # Last 10 frames before this one
        caller_info.append(f"  {frame.filename}:{frame.lineno} in {frame.name}")

    trace_log(f"CANCEL called on task '{task_name}' (coro: {coro_name})", "CANCEL")
    trace_log(f"Cancel message: {msg}", "CANCEL")
    trace_log("Called from:\n" + "\n".join(caller_info), "CANCEL")

    # Call original
    return original_task_cancel(self, msg)


# Apply monkey patch
asyncio.Task.cancel = traced_cancel

# Patch asyncio.wait_for to trace timeouts
original_wait_for = asyncio.wait_for


async def traced_wait_for(coro, timeout):
    """Traced version of asyncio.wait_for"""
    trace_log(f"wait_for started with timeout={timeout}s for {coro}", "WAIT_FOR")
    start_time = time.time()

    try:
        result = await original_wait_for(coro, timeout)
        elapsed = time.time() - start_time
        trace_log(f"wait_for completed successfully after {elapsed:.3f}s", "WAIT_FOR")
        return result
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        trace_log(
            f"wait_for TIMED OUT after {elapsed:.3f}s (timeout was {timeout}s)",
            "TIMEOUT",
        )
        raise
    except asyncio.CancelledError:
        elapsed = time.time() - start_time
        trace_log(f"wait_for CANCELLED after {elapsed:.3f}s", "CANCELLED")
        raise


asyncio.wait_for = traced_wait_for

# Import and patch operation manager
from mcp_second_brain.operation_manager import OperationManager

# Patch run_with_timeout
original_run_with_timeout = OperationManager.run_with_timeout


async def traced_run_with_timeout(
    self, operation_id: str, coro: Coroutine, timeout: int
):
    """Traced version of run_with_timeout"""
    trace_log(f"Operation {operation_id} starting with timeout={timeout}s", "OPERATION")

    try:
        result = await original_run_with_timeout(self, operation_id, coro, timeout)
        trace_log(f"Operation {operation_id} completed successfully", "OPERATION")
        return result
    except asyncio.CancelledError:
        trace_log(f"Operation {operation_id} got CancelledError", "CANCELLED")
        raise
    except Exception as e:
        trace_log(
            f"Operation {operation_id} failed with {type(e).__name__}: {e}", "ERROR"
        )
        raise


OperationManager.run_with_timeout = traced_run_with_timeout

# Import and patch FastMCP response handling
try:
    from fastmcp import FastMCP

    # Find and patch the response sending method
    if hasattr(FastMCP, "_send_response"):
        original_send_response = FastMCP._send_response

        async def traced_send_response(self, *args, **kwargs):
            trace_log(
                f"FastMCP._send_response called with args={args}, kwargs={kwargs}",
                "RESPONSE",
            )
            try:
                result = await original_send_response(self, *args, **kwargs)
                trace_log("FastMCP._send_response completed successfully", "RESPONSE")
                return result
            except Exception as e:
                trace_log(
                    f"FastMCP._send_response failed with {type(e).__name__}: {e}",
                    "ERROR",
                )
                raise

        FastMCP._send_response = traced_send_response
except Exception as e:
    trace_log(f"Failed to patch FastMCP: {e}", "WARNING")

# Patch tool executor
from mcp_second_brain.tools.executor import Executor

original_execute_tool = Executor.execute_tool


async def traced_execute_tool(self, tool_id: str, arguments: dict[str, Any]):
    """Traced version of execute_tool"""
    trace_log(f"Tool execution starting: {tool_id}", "TOOL")

    try:
        result = await original_execute_tool(self, tool_id, arguments)
        trace_log(f"Tool execution completed: {tool_id}", "TOOL")
        return result
    except asyncio.CancelledError:
        trace_log(f"Tool execution CANCELLED: {tool_id}", "CANCELLED")
        raise
    except Exception as e:
        trace_log(
            f"Tool execution failed: {tool_id} - {type(e).__name__}: {e}", "ERROR"
        )
        raise


Executor.execute_tool = traced_execute_tool

trace_log("All patches applied. Starting server...")

# Now run the actual server
from mcp_second_brain.server import main

if __name__ == "__main__":
    trace_log("Calling main()...")
    main()
