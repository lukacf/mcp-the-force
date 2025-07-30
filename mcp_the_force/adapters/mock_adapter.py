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

    # class-level store:  {session_id: [ {"role": "...", "content": "..."} ]}
    _session_histories: Dict[str, List[Dict[str, str]]] = {}

    def __init__(self, model_name: str):
        """Initialize with model name and set appropriate capabilities."""
        self.model_name = model_name
        self.display_name = f"Mock {model_name}"

        # Get capabilities for the model being mocked
        self.capabilities, self.param_class = self._get_model_capabilities(model_name)

    def _get_model_capabilities(
        self, model_name: str
    ) -> tuple[AdapterCapabilities, type]:
        """Get the appropriate capabilities and param class for the model."""
        # Default capabilities
        default_capabilities = AdapterCapabilities(
            supports_tools=True,
            supports_streaming=False,
            max_context_window=1_000_000,
            description="Mock adapter for testing",
        )

        # Try to get the actual model capabilities
        try:
            # Check OpenAI models
            from .openai.definitions import OPENAI_MODEL_CAPABILITIES, OpenAIToolParams

            if model_name in OPENAI_MODEL_CAPABILITIES:
                return OPENAI_MODEL_CAPABILITIES[model_name], OpenAIToolParams

            # Check Gemini models
            from .google.definitions import GEMINI_MODEL_CAPABILITIES, GeminiToolParams

            if model_name in GEMINI_MODEL_CAPABILITIES:
                return GEMINI_MODEL_CAPABILITIES[model_name], GeminiToolParams

            # Check Grok models
            from .xai.definitions import GROK_MODEL_CAPABILITIES, GrokToolParams

            if model_name in GROK_MODEL_CAPABILITIES:
                return GROK_MODEL_CAPABILITIES[model_name], GrokToolParams
        except ImportError:
            pass

        # Fall back to default capabilities and MockToolParams
        return default_capabilities, MockToolParams

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

        # Check if messages were passed in kwargs (from executor)
        if "messages" in kwargs and kwargs["messages"]:
            # Use the messages from the executor which contain full conversation history
            history = kwargs["messages"].copy()
            # The current prompt should already be in messages as the last user message
        else:
            # Fallback to MockAdapter's own history tracking
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

        # For the prompt field, include the full conversation context
        # This is what the tests expect to see
        full_prompt = pretty_history

        # ------------------------------------------------------------------
        # 4. Produce a "mock response" that includes all the metadata
        # ------------------------------------------------------------------
        # Extract adapter kwargs for backward compatibility with tests
        adapter_kwargs = {
            "session_id": session_id,
            "temperature": getattr(params, "temperature", 0.5),
            "timeout": kwargs.get("timeout", 300),
        }

        # Add system_instruction if present in kwargs
        if "system_instruction" in kwargs:
            adapter_kwargs["system_instruction"] = kwargs["system_instruction"]

        # Build messages array for Gemini compatibility
        messages = []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        adapter_kwargs["messages"] = messages

        # The integration tests define "turn_count" as *user* turn index.
        # Count user messages only, *before* we append our synthetic assistant reply
        turn_count = sum(1 for msg in history if msg.get("role") == "user")

        metadata = {
            "mock": True,  # Add this field that the test expects
            "model": self.model_name,
            "prompt": full_prompt,  # Use full conversation history for tests
            "prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt,
            "prompt_length": len(full_prompt),
            "session_id": session_id,
            "vector_store_ids": sorted(vector_store_ids) if vector_store_ids else [],
            "kwargs": sorted(kwargs.keys()),
            "conversation": pretty_history,
            "turn_count": turn_count,
            "adapter_kwargs": adapter_kwargs,  # Add this for test compatibility
        }

        # Add mock response to history
        mock_response = json.dumps(metadata)  # Return pure JSON for integration tests
        if session_id:
            # For history, save a simpler response to avoid SQLite size limits
            simple_response = f"Mock response from {self.model_name}"
            history.append({"role": "assistant", "content": simple_response})
            session_key = f"{session_id}:{self.model_name}"
            self._session_histories[session_key] = history

            # Save to unified session cache for multi-turn support
            from ..unified_session_cache import UnifiedSessionCache

            # Save the conversation history to the unified cache
            await UnifiedSessionCache.set_history(
                ctx.project, ctx.tool, session_id, history
            )

        # Return dict format as per MCPAdapter protocol
        return {"content": mock_response}
