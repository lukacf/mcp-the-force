#!/usr/bin/env python3
"""Debug script to trace cancellation flow in MCP server."""

import asyncio
import sys
import os
import logging

# Add the project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_second_brain.operation_manager import operation_manager

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def simulate_long_operation():
    """Simulate a long-running operation like o3 model call."""
    print("Starting long operation...")
    try:
        await asyncio.sleep(30)  # Simulate 30 second operation
        print("Operation completed successfully")
        return "Success"
    except asyncio.CancelledError:
        print("Operation was cancelled!")
        raise


async def test_cancellation():
    """Test the cancellation flow."""
    print("=== Testing Operation Manager Cancellation ===")

    # Start the operation
    task = asyncio.create_task(
        operation_manager.run_with_timeout(
            "test_operation_001",
            simulate_long_operation(),
            timeout=60.0,  # 1 minute timeout
        )
    )

    # Wait 5 seconds then cancel
    print("Waiting 5 seconds before cancelling...")
    await asyncio.sleep(5)

    print("Cancelling the task...")
    task.cancel()

    # Try to get the result
    try:
        result = await task
        print(f"Got result: {result}")
    except asyncio.CancelledError:
        print("Task was cancelled as expected")
    except Exception as e:
        print(f"Unexpected error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(test_cancellation())
