"""Bridge adapter that connects protocol-based Grok adapter to legacy system."""

from typing import Any, Dict, List, Optional
from .base import BaseAdapter
from .grok_new.adapter import GrokAdapter as ProtocolGrokAdapter
from .protocol import CallContext
from .tool_dispatcher import ToolDispatcher


class GrokBridgeAdapter(BaseAdapter):
    """Bridge that wraps the protocol-based Grok adapter for legacy compatibility.

    This allows us to use the new protocol-based adapter in the existing
    system that expects BaseAdapter inheritance.
    """

    def __init__(self, model: str):
        """Initialize bridge with protocol adapter."""
        super().__init__()

        # Create the protocol-based adapter
        self.protocol_adapter = ProtocolGrokAdapter(model)

        # Copy attributes from protocol adapter
        self.model_name = self.protocol_adapter.model_name
        self.context_window = (
            self.protocol_adapter.capabilities.max_context_window or 131_000
        )
        self.supports_functions = self.protocol_adapter.capabilities.supports_functions
        self.supports_live_search = (
            self.protocol_adapter.capabilities.supports_live_search
        )
        self.supports_streaming = self.protocol_adapter.capabilities.supports_streaming
        self.supports_reasoning_effort = (
            self.protocol_adapter.capabilities.supports_reasoning_effort
        )
        self.description_snippet = self.protocol_adapter.capabilities.description

    async def generate(
        self,
        prompt: str,
        vector_store_ids: Optional[List[str]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        search_mode: Optional[str] = None,
        search_parameters: Optional[Dict[str, Any]] = None,
        return_citations: bool = True,
        structured_output_schema: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate using the protocol adapter.

        This method translates between the legacy interface and the new
        protocol-based interface.
        """

        # Create parameter instance as a simple object
        # (The param_class uses Route descriptors, not meant for direct instantiation)
        from types import SimpleNamespace

        params = SimpleNamespace(
            instructions=prompt,
            output_format="",
            context=[],
            session_id=session_id or "",
            search_mode=search_mode,
            search_parameters=search_parameters,
            return_citations=return_citations,
            temperature=temperature,
            reasoning_effort=kwargs.get("reasoning_effort"),
            disable_memory_search=kwargs.get("disable_memory_search", False),
            structured_output_schema=structured_output_schema,
        )

        # Create context
        ctx = CallContext(
            session_id=session_id or "",
            vector_store_ids=vector_store_ids,
        )

        # Create tool dispatcher
        tool_dispatcher = ToolDispatcher(vector_store_ids=vector_store_ids)

        # Call protocol adapter
        return await self.protocol_adapter.generate(
            prompt=prompt,
            params=params,  # type: ignore[arg-type]
            ctx=ctx,
            tool_dispatcher=tool_dispatcher,
            messages=messages,
            system_instruction=system_instruction,
            **kwargs,
        )
