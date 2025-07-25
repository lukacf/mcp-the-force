"""Protocol for local utility services.

These are tools that execute locally (database queries, file operations, etc.)
rather than calling external AI models. They implement a simple execute() method
and can be exposed both as MCP tools and as built-in functions for AI models.
"""

from typing import Protocol, Any


class LocalService(Protocol):
    """Protocol for local utility services."""

    async def execute(self, **kwargs: Any) -> str:
        """Execute the service and return a string result.

        Args:
            **kwargs: Service-specific parameters

        Returns:
            String result that can be displayed to users
        """
        ...
