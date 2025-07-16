#!/usr/bin/env python3
"""
Debug script that simulates MCP server cancellation flow.
We'll set breakpoints here to understand the exact sequence.
"""

import asyncio
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the actual server components
from mcp_second_brain.tools.executor import executor


# Simulate what happens in the MCP server
async def simulate_mcp_tool_call():
    """Simulate an MCP tool call that gets cancelled."""
    print("=== Simulating MCP Tool Call Flow ===")

    # This simulates what happens when FastMCP calls a tool
    tool_params = {
        "instructions": "Analyze something complex that takes time",
        "output_format": "Detailed analysis",
        "context": [],
        "session_id": "debug-session-001",
    }

    try:
        # This is similar to what happens in the server
        print("1. Starting tool execution...")
        result = await executor.execute_tool(
            "chat_with_gemini25_flash",  # Using a fast model for testing
            tool_params,
        )
        print(f"2. Tool completed successfully: {result[:100]}...")
        return result

    except asyncio.CancelledError:
        print("3. Tool execution was CANCELLED")
        # This is where we need to understand what happens
        raise
    except Exception as e:
        print(f"4. Tool execution failed: {type(e).__name__}: {e}")
        raise


async def simulate_cancellation_after_delay():
    """Simulate what happens when user aborts after ~14 seconds."""
    # Create the task
    tool_task = asyncio.create_task(simulate_mcp_tool_call())

    # Wait 2 seconds then cancel (simulating the 14-second delay)
    print("\nWaiting 2 seconds before simulating cancellation...")
    await asyncio.sleep(2)

    print("\n*** SIMULATING USER ABORT ***")
    print("(In real scenario, this happens ~14 seconds after tool start)")

    # Cancel the task
    tool_task.cancel()

    # See what happens
    try:
        result = await tool_task
        print(f"\nUnexpected: Got result despite cancellation: {result}")
    except asyncio.CancelledError:
        print("\nAs expected: Task was cancelled")
        # In the real server, what happens here is critical
        # Does it send an error response? Or a success response?


if __name__ == "__main__":
    print("Starting debug simulation...")
    print("Set breakpoints in operation_manager.py line 59-71")
    print("-" * 60)

    asyncio.run(simulate_cancellation_after_delay())
