"""Mock adapter for integration testing that now simulates multi-turn memory."""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from .capabilities import AdapterCapabilities
from .protocol import CallContext, ToolDispatcher


@dataclass
class MockToolParams:
    """Simple parameters for mock adapter testing."""

    # Base parameters
    instructions: Optional[str] = None
    output_format: Optional[str] = None
    context: Optional[List[str]] = None
    session_id: Optional[str] = None

    # Mock-specific parameters for testing
    temperature: float = 0.5
    disable_memory_search: bool = False


class MockAdapter:
    """Lightweight mock that echoes metadata and conversation history.

    This mock adapter implements the MCPAdapter protocol for testing.
    """

    description_snippet = "Mock adapter for testing"
    context_window = 1_000_000

    # MCPAdapter protocol properties
    capabilities = AdapterCapabilities(
        native_file_search=False,
        supports_functions=True,
        supports_streaming=False,
        max_context_window=1_000_000,
        description="Mock adapter for testing",
    )
    param_class = MockToolParams  # Simple params for testing
    display_name = "Mock Adapter"

    # class-level store:  {session_id: [ {"role": "...", "content": "..."} ]}
    _session_histories: Dict[str, List[Dict[str, str]]] = {}

    def __init__(self, model_name: str):
        """Initialize with model name."""
        self.model_name = model_name
        self.display_name = f"Mock {model_name}"

    async def generate(
        self,
        prompt: str,
        params: Any,  # Instance of param_class
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Return JSON metadata, including a synthetic prompt that contains
        all prior turns so that the integration tests can assert on it.

        Now implements the MCPAdapter protocol.
        """

        # Extract data from the new protocol parameters
        session_id = ctx.session_id if ctx.session_id else None
        vector_store_ids = ctx.vector_store_ids

        # ------------------------------------------------------------------
        # 1. Load history for this session (if any)
        #    Use both session_id and model_name to ensure isolation between models
        # ------------------------------------------------------------------
        history: List[Dict[str, str]] = []
        if session_id:
            session_key = f"{session_id}:{self.model_name}"
            history = self._session_histories.get(session_key, []).copy()

        # ------------------------------------------------------------------
        # 2. For testing, always append to MockAdapter's own history.
        #    This ensures conversation accumulation works regardless of real session cache state.
        # ------------------------------------------------------------------
        history.append({"role": "user", "content": prompt})

        # Persist history for later turns
        if session_id:
            session_key = f"{session_id}:{self.model_name}"
            self._session_histories[session_key] = history

        # ------------------------------------------------------------------
        # 3. Flatten history so the tests can look for previous-turn tokens
        # ------------------------------------------------------------------
        pretty_history = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in history
        )

        # ------------------------------------------------------------------
        # 4. Produce a "mock response" that includes all the metadata
        # ------------------------------------------------------------------
        metadata = {
            "model": self.model_name,
            "prompt": prompt,
            "prompt_length": len(prompt),
            "session_id": session_id,
            "vector_store_ids": sorted(vector_store_ids) if vector_store_ids else [],
            "kwargs": sorted(kwargs.keys()),
            "conversation": pretty_history,
            "turn_count": len(history),
        }

        # Add mock response to history
        mock_response = f"Mock response with metadata: {json.dumps(metadata)}"
        if session_id:
            history.append({"role": "assistant", "content": mock_response})
            session_key = f"{session_id}:{self.model_name}"
            self._session_histories[session_key] = history

        # Return dict format as per MCPAdapter protocol
        return {"content": mock_response}
