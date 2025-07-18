#!/usr/bin/env python3
"""Test the async VictoriaLogs handler directly."""

import asyncio
import logging
import os
import time
from mcp_second_brain.utils.async_victoria import VictoriaAsyncHandler, QUEUE

# Set up test logger
logger = logging.getLogger("test_logger")
logger.setLevel(logging.DEBUG)

# Add file handler for output we can check
file_handler = logging.FileHandler("test_victoria.log", mode="w")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
logger.addHandler(file_handler)

# Set the VictoriaLogs URL
os.environ["VICTORIA_URL"] = (
    "http://localhost:9428/insert/loki/api/v1/push?_stream_fields=app,instance_id"
)

# Add the async victoria handler
victoria_handler = VictoriaAsyncHandler()
victoria_handler.setLevel(logging.DEBUG)
victoria_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)

# Add filters to set the required attributes
victoria_handler.addFilter(lambda record: setattr(record, "app", "test-app") or True)
victoria_handler.addFilter(
    lambda record: setattr(record, "instance_id", "test-001") or True
)

logger.addHandler(victoria_handler)


async def test_logging_flood():
    """Test what happens when we flood the logger like in the duplicate files scenario."""
    print("Starting logging flood test...")
    print(f"Initial queue size: {QUEUE.qsize()}")

    # Simulate the duplicate file scenario
    print("\n=== Simulating duplicate file logging (87 files) ===")
    start_time = time.time()

    for i in range(87):
        logger.info(f"Skipping duplicate file: /path/to/file_{i}.py")
        if i % 10 == 0:
            print(f"Logged {i} messages, queue size: {QUEUE.qsize()}")

    print(f"\nFinished logging 87 messages in {time.time() - start_time:.3f}s")
    print(f"Queue size after logging: {QUEUE.qsize()}")

    # Give the drain task time to process
    print("\nWaiting for drain task to process...")
    await asyncio.sleep(2)
    print(f"Queue size after 2s: {QUEUE.qsize()}")

    # Now simulate a second batch (like second query)
    print("\n=== Simulating second batch (another 87 files) ===")
    start_time = time.time()

    for i in range(87):
        logger.info(f"Skipping duplicate file (2nd query): /path/to/file_{i}.py")
        if i % 10 == 0:
            print(f"Logged {i} messages, queue size: {QUEUE.qsize()}")

    print(f"\nFinished second batch in {time.time() - start_time:.3f}s")
    print(f"Queue size after second batch: {QUEUE.qsize()}")

    # Test with a really tight loop
    print("\n=== Testing tight loop (1000 messages) ===")
    start_time = time.time()

    for i in range(1000):
        logger.debug(f"Tight loop message {i}")
        if i % 100 == 0:
            print(f"Logged {i} messages, queue size: {QUEUE.qsize()}")

    print(f"\nFinished tight loop in {time.time() - start_time:.3f}s")
    print(f"Final queue size: {QUEUE.qsize()}")

    # Wait for final drain
    print("\nWaiting for final drain...")
    await asyncio.sleep(3)
    print(f"Queue size after final wait: {QUEUE.qsize()}")


async def test_drain_task_health():
    """Check if the drain task is actually running."""
    print("\n=== Checking drain task health ===")

    # Check if drain task exists
    if hasattr(victoria_handler, "_drain_task"):
        task = victoria_handler._drain_task
        if task:
            print(f"Drain task exists: {task}")
            print(f"Task done: {task.done()}")
            print(f"Task cancelled: {task.cancelled()}")
            if task.done() and not task.cancelled():
                try:
                    task.result()
                except Exception as e:
                    print(f"Drain task failed with: {e}")
        else:
            print("No drain task found!")
    else:
        print("Handler has no _drain_task attribute!")

    # List all running tasks
    print("\nAll running tasks:")
    for task in asyncio.all_tasks():
        print(f"  - {task.get_name()}: {task}")


async def main():
    print("Testing Async VictoriaLogs Handler")
    print("=" * 50)

    # Test logging flood
    await test_logging_flood()

    # Check drain task health
    await test_drain_task_health()

    print("\n" + "=" * 50)
    print("Test complete! Check test_victoria.log for output")

    # Count lines in log file
    with open("test_victoria.log", "r") as f:
        line_count = len(f.readlines())
    print(f"Total lines written to log file: {line_count}")


if __name__ == "__main__":
    asyncio.run(main())
