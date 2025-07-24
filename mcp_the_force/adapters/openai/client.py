"""Process-safe OpenAI client wrapper."""

import asyncio
import weakref
from typing import Optional, Dict, Any
from openai import AsyncOpenAI
import httpx
import logging

logger = logging.getLogger(__name__)


class OpenAIClientFactory:
    """
    Manages one AsyncOpenAI client instance per event loop.
    This is critical for multi-worker servers (e.g., Uvicorn with workers > 1),
    where each worker process runs its own event loop.
    Using a weakref dictionary ensures that if a loop is destroyed, its
    client instance is garbage collected.
    """

    _instances: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncOpenAI]" = (
        weakref.WeakKeyDictionary()
    )
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls, api_key: Optional[str] = None) -> AsyncOpenAI:
        """Get the client for the currently running event loop.

        Args:
            api_key: Optional API key. If not provided, the client will use
                    the OPENAI_API_KEY environment variable.

        Returns:
            AsyncOpenAI client instance for the current event loop.
        """
        loop = asyncio.get_running_loop()

        # Fast path: return existing instance
        if loop in cls._instances:
            return cls._instances[loop]

        async with cls._lock:
            # Re-check after acquiring the lock to handle race conditions.
            if loop in cls._instances:
                return cls._instances[loop]

            # Configure robust HTTP transport with connection pooling.
            # CRITICAL: keepalive_expiry=60.0 discards idle connections after 60s
            # This prevents reusing stale connections that cause hangs
            limits = httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=60.0,  # Discard idle connections after 60 seconds
            )

            # Set explicit timeouts to prevent indefinite hangs on stale connections
            # These replace the dangerous None values that wait forever
            timeout = httpx.Timeout(
                connect=20.0,  # 20s to establish connection
                write=60.0,  # 60s to write request
                read=180.0,  # 3 minutes for response (was None - wait forever)
                pool=60.0,  # 60s to get connection from pool (was None - wait forever)
            )

            # Enable retries for transient errors
            transport = httpx.AsyncHTTPTransport(retries=3)

            # The http_client will be managed by the AsyncOpenAI instance.
            http_client = httpx.AsyncClient(
                limits=limits, timeout=timeout, transport=transport
            )

            client_kwargs: Dict[str, Any] = {
                "http_client": http_client,
                "max_retries": 3,  # SDK-level retries
                "timeout": 3600.0,  # 1 hour timeout for deep research models
            }

            if api_key:
                client_kwargs["api_key"] = api_key

            client = AsyncOpenAI(**client_kwargs)
            cls._instances[loop] = client

            logger.info(f"Created new OpenAI client for event loop {id(loop)}")
            return client

    @classmethod
    async def close_all(cls):
        """Close all client instances. Useful for cleanup in tests."""
        async with cls._lock:
            for client in cls._instances.values():
                if hasattr(client, "_client") and client._client:
                    # Handle both real and mocked clients
                    if hasattr(client._client, "aclose"):
                        close_coro = client._client.aclose()
                        if asyncio.iscoroutine(close_coro):
                            await close_coro
            cls._instances.clear()
            logger.info("Closed all OpenAI client instances")
