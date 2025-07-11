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
        incoming_messages = kwargs.get("messages")  # may be None

        # ------------------------------------------------------------------
        # 1. Load history for this session (if any)
        # ------------------------------------------------------------------
        history: List[Dict[str, str]] = []
        if session_id:
            history = self._session_histories.get(session_id, []).copy()

        # ------------------------------------------------------------------
        # 2. Decide what the *current* user message is and update history
        # ------------------------------------------------------------------
        if incoming_messages and isinstance(incoming_messages, list):
            # The executor (or Grok adapter in prod) has already built a
            # full message list – use it as the new history.
            history = incoming_messages
        else:
            # No structured messages supplied → treat the raw `prompt`
            # (minus any developer/system prefix) as the user's turn.
            history.append({"role": "user", "content": prompt})

        # Persist history for later turns
        if session_id:
            self._session_histories[session_id] = history

        # ------------------------------------------------------------------
        # 3. Flatten history so the tests can look for previous-turn tokens
        # ------------------------------------------------------------------
        pretty_history = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history
        )

        # ------------------------------------------------------------------
        # 4. Return the same JSON envelope the tests already expect
        # ------------------------------------------------------------------
        return json.dumps(
            {
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
                # Echo **all** kwargs so tests can inspect temperature, etc.
                "adapter_kwargs": kwargs or {},
            },
            indent=2,
        )
