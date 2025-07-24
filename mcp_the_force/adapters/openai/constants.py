"""Constants for OpenAI adapter."""

import os
import asyncio

# --- Concurrency ---
# A global (per-worker) semaphore to limit total concurrent tool executions.
# Protects against API rate limits and local resource exhaustion.
raw_parallel = int(os.getenv("MAX_PARALLEL_TOOL_EXEC", "8"))
MAX_PARALLEL_TOOL_EXEC = max(raw_parallel, 1)  # Clamp minimum to 1 for safety.
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
