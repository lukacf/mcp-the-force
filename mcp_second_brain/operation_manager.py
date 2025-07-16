"""Manage long-running operations with proper cancellation support."""

import asyncio
import logging
import time
from typing import Dict, Optional, Any, Coroutine

logger = logging.getLogger(__name__)


class OperationManager:
    """Manages long-running operations and ensures they can be cancelled."""

    def __init__(self):
        self.active_operations: Dict[str, asyncio.Task] = {}
        self.operation_start_times: Dict[str, float] = {}
        self._monitor_task: Optional[asyncio.Task] = None

    async def run_with_timeout(
        self, operation_id: str, coro: Coroutine[Any, Any, Any], timeout: float
    ) -> Any:
        """Run an operation with timeout and cancellation support."""
        logger.debug(
            f"run_with_timeout called: operation_id={operation_id}, timeout={timeout}"
        )

        # Create a task from the coroutine so it can be tracked
        task = asyncio.create_task(coro)
        self.active_operations[operation_id] = task
        self.operation_start_times[operation_id] = time.time()

        logger.info(f"Starting operation {operation_id} with {timeout}s timeout")
        logger.debug(f"Task created and registered: {operation_id}")

        try:
            # Use wait_for on the task
            result = await asyncio.wait_for(task, timeout=timeout)
            logger.info(f"Operation {operation_id} completed successfully")
            logger.debug(f"Operation completed successfully: {operation_id}")
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Operation {operation_id} timed out after {timeout}s")
            logger.debug(f"Operation timed out: {operation_id}")
            raise
        except asyncio.CancelledError:
            logger.info(f"Operation {operation_id} was cancelled by MCP.")
            logger.debug(f"Operation cancelled by MCP, re-raising: {operation_id}")
            # Explicitly cancel the inner task to ensure clean shutdown
            if not task.done():
                task.cancel()
                logger.debug(f"Explicitly cancelled inner task: {operation_id}")
            # Re-raise to let the cancellation propagate properly
            raise
        except Exception as e:
            logger.error(f"Operation {operation_id} failed: {e}")
            logger.debug(
                f"Operation failed with error: {operation_id} - {type(e).__name__}: {e}"
            )
            raise
        finally:
            self.active_operations.pop(operation_id, None)
            self.operation_start_times.pop(operation_id, None)
            logger.debug(f"Cleaned up operation: {operation_id}")

    async def cancel_operation(self, operation_id: str):
        """Cancel a specific operation."""
        task = self.active_operations.get(operation_id)
        if task and not task.done():
            logger.info(f"Cancelling operation {operation_id}")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def cancel_all_operations(self):
        """Cancel all active operations."""
        if not self.active_operations:
            return

        logger.warning(f"Cancelling {len(self.active_operations)} active operations")

        for op_id, task in list(self.active_operations.items()):
            if not task.done():
                task.cancel()

        # Wait for all cancellations to complete
        tasks = [task for task in self.active_operations.values() if not task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.active_operations.clear()
        self.operation_start_times.clear()

    def get_status(self) -> Dict[str, Any]:
        """Get status of all operations."""
        status = {}
        now = time.time()

        for op_id, task in self.active_operations.items():
            start_time = self.operation_start_times.get(op_id, now)
            duration = now - start_time

            status[op_id] = {
                "running": not task.done(),
                "duration": duration,
                "cancelled": task.cancelled() if task.done() else False,
            }

        return status

    async def start_monitoring(self):
        """Start monitoring operations for health checks."""

        async def monitor():
            while True:
                # Log status every 30 seconds if there are active operations
                if self.active_operations:
                    status = self.get_status()
                    logger.debug(f"Active operations: {status}")

                await asyncio.sleep(30)

        if not self._monitor_task:
            self._monitor_task = asyncio.create_task(monitor())

    def stop_monitoring(self):
        """Stop monitoring operations."""
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None


# Global operation manager instance
operation_manager = OperationManager()
logger.debug("Global operation_manager instance created")
