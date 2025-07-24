# mcp_the_force/utils/scope_manager.py
"""Scope management for request-local context using contextvars."""

import contextlib
import uuid
from contextvars import ContextVar
from typing import Optional, AsyncGenerator

# The ContextVar to hold the unique scope ID for the current async task.
_current_scope_id: ContextVar[Optional[str]] = ContextVar(
    "current_scope_id", default=None
)


class ScopeManager:
    """
    Manages deduplication scope using an asyncio.ContextVar for task-local isolation.
    """

    @contextlib.asynccontextmanager
    async def scope(self, scope_id: Optional[str]) -> AsyncGenerator[None, None]:
        """
        An async context manager to set the deduplication scope for a block of code.
        If the provided scope_id is None, a unique, single-use ID will be generated.
        """
        # If no specific scope is provided, generate a new one to ensure isolation.
        final_scope_id = scope_id or f"isolated_{uuid.uuid4().hex}"
        token = _current_scope_id.set(final_scope_id)
        try:
            yield
        finally:
            _current_scope_id.reset(token)

    def get_scope_id(self) -> str:
        """
        Gets the current scope ID. If no scope is set, it falls back to:
        1. The instance_id (for Claude direct tool calls)
        2. A new unique UUID (for other isolated cases)
        """
        scope_id = _current_scope_id.get()
        if scope_id:
            return scope_id

        # Try to use instance_id for Claude direct tool calls
        try:
            from ..logging.setup import get_instance_id

            instance_id = get_instance_id()
            if instance_id:
                return f"instance_{instance_id}"
        except ImportError:
            pass

        # Fallback to a new, unique scope if none is set in the context.
        return f"isolated_{uuid.uuid4().hex}"


# Singleton instance for global use
scope_manager = ScopeManager()
