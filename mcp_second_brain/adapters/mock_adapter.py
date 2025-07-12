"""Mock adapter for integration testing that now simulates multi-turn memory."""

import json
from typing import Dict, List
from .base import BaseAdapter


class MockAdapter(BaseAdapter):
    """Lightweight mock that echoes metadata and conversation history."""

    description_snippet = "Mock adapter for testing"
    context_window = 1_000_000

    # class-level store:  {session_id: [ {"role": "...", "content": "..."} ]}
    _session_histories: Dict[str, List[Dict[str, str]]] = {}

    def __init__(self, model_name: str):
        """Initialize with model name."""
        self.model_name = model_name

    async def generate(self, prompt: str, vector_store_ids=None, **kwargs):
        """Return JSON metadata, including a synthetic prompt that contains
        all prior turns so that the integration tests can assert on it."""

        session_id: str | None = kwargs.get("session_id")

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
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history
        )

        # ------------------------------------------------------------------
        # 4. Return appropriate response type based on model
        # ------------------------------------------------------------------
        response_payload = {
            "mock": True,
            "model": self.model_name,
            "prompt": pretty_history,
            "prompt_preview": (
                pretty_history[:200] + "..."
                if len(pretty_history) > 200
                else pretty_history
            ),
            "prompt_length": len(pretty_history),
            "vector_store_ids": vector_store_ids,
            "adapter_kwargs": kwargs or {},
        }

        # For OpenAI models, the executor expects a dictionary with 'content' and 'response_id'.
        # This makes the mock behave like the real OpenAIAdapter.
        if self.model_name in ["o3", "o3-pro", "gpt-4.1"]:
            return {
                "content": json.dumps(response_payload, indent=2),
                "response_id": f"resp_{session_id or 'none'}_{len(history)}",
            }

        # For other models, the executor expects a string (JSON string in this case).
        return json.dumps(response_payload, indent=2)
