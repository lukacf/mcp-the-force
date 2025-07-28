"""Constants for OpenAI adapter."""

import asyncio
from ...config import get_settings

# --- Concurrency ---
# A global (per-worker) semaphore to limit total concurrent tool executions.
# Protects against API rate limits and local resource exhaustion.


def _get_max_parallel_tool_exec():
    """Get max parallel tool exec from settings, with lazy loading."""
    try:
        settings = get_settings()
        value = settings.openai.max_parallel_tool_exec
        # Handle case where value might be a MagicMock in tests
        if hasattr(value, "__int__"):
            value = int(value)
        elif not isinstance(value, int):
            value = 8  # Default fallback
        return max(value, 1)  # Clamp minimum to 1 for safety
    except Exception:
        return 8  # Default fallback


MAX_PARALLEL_TOOL_EXEC = _get_max_parallel_tool_exec()
GLOBAL_TOOL_LIMITER = asyncio.Semaphore(MAX_PARALLEL_TOOL_EXEC)

# --- Polling ---
# Start polling for background jobs after 3 seconds
INITIAL_POLL_DELAY_SEC = 3.0
# Cap the exponential backoff for polling at 30 seconds
MAX_POLL_INTERVAL_SEC = 30.0

# --- Timeouts ---
# Models with longer timeouts than this threshold use background mode
STREAM_TIMEOUT_THRESHOLD = 180  # seconds
# Default timeout for API calls
DEFAULT_TIMEOUT = 300  # seconds
