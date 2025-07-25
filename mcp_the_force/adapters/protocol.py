"""Adapter protocol definition."""

from typing import Protocol, Any, Dict, Optional, List
from dataclasses import dataclass
from .capabilities import AdapterCapabilities


@dataclass
class CallContext:
    """Context passed to adapters during generation."""

    session_id: str
    vector_store_ids: Optional[List[str]] = None
    tool_call_id: Optional[str] = None
    # Add more context as needed


class ToolDispatcher(Protocol):
    """Interface for tool execution."""

    def get_tool_declarations(self, adapter_type: str) -> List[Dict[str, Any]]:
        """Get tool declarations in the format expected by the adapter."""
        ...

    async def execute(
        self, tool_name: str, tool_args: str, context: CallContext
    ) -> Any:
        """Execute a tool and return its result."""
        ...


class MCPAdapter(Protocol):
    """Interface that all adapters must satisfy.

    This is a Protocol (structural typing) - adapters don't need to
    inherit from this, they just need to have these attributes/methods.
    """

    capabilities: AdapterCapabilities
    param_class: type
    display_name: str
    model_name: str

    async def generate(
        self,
        prompt: str,
        params: Any,  # Instance of param_class
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate response from the model.

        Args:
            prompt: User prompt
            params: Validated parameters (instance of param_class)
            ctx: Call context including session_id, vector_store_ids
            tool_dispatcher: Interface for executing tools
            **kwargs: Additional adapter-specific parameters

        Returns:
            Dict with at least {"content": str} and optionally
            {"citations": List, "usage": Dict, etc.}
        """
        ...
