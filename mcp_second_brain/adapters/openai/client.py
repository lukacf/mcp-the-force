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
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)

            # Match the current timeout configuration:
            # connect=30, write=30, read=None (disabled for streaming)
            timeout = httpx.Timeout(
                connect=30.0,
                write=30.0,
                read=None,  # Disable read timeout for long-running streaming
                pool=None,
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
