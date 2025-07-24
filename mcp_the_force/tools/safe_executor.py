"""
Wrapper to make tool execution completely safe from cancellation issues.
"""

import asyncio
import logging
from typing import Any
from .executor import ToolExecutor
from .registry import ToolMetadata

logger = logging.getLogger(__name__)


class SafeExecutor(ToolExecutor):
    """Executor that never lets CancelledError escape."""

    async def execute(self, metadata: ToolMetadata, **kwargs: Any) -> str:
        """Execute tool with complete cancellation safety."""
        try:
            # Call parent's execute method
            return await super().execute(metadata, **kwargs)
        except asyncio.CancelledError:
            logger.info(
                f"[SAFE] Tool {metadata.id} cancelled - returning empty success"
            )
            # Never let CancelledError escape - always return success
            return ""
        except Exception as e:
            # Let other exceptions through
            logger.error(
                f"[SAFE] Tool {metadata.id} failed with {type(e).__name__}: {e}"
            )
            raise


# Create singleton instance
safe_executor = SafeExecutor()
