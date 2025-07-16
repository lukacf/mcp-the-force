"""
Wrapper to make tool execution completely safe from cancellation issues.
"""

import asyncio
import logging
from .executor import Executor

logger = logging.getLogger(__name__)


class SafeExecutor(Executor):
    """Executor that never lets CancelledError escape."""

    async def execute_tool(self, tool_id: str, arguments: dict) -> str:
        """Execute tool with complete cancellation safety."""
        try:
            # Call parent's execute_tool
            return await super().execute_tool(tool_id, arguments)
        except asyncio.CancelledError:
            logger.info(f"[SAFE] Tool {tool_id} cancelled - returning empty success")
            # Never let CancelledError escape - always return success
            return ""
        except Exception as e:
            # Let other exceptions through
            logger.error(f"[SAFE] Tool {tool_id} failed with {type(e).__name__}: {e}")
            raise


# Create singleton instance
safe_executor = SafeExecutor()
