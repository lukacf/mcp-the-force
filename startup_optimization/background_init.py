"""Background initialization for non-blocking startup."""

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def optimized_server_lifespan(server) -> AsyncIterator[None]:
    """Optimized lifespan context manager with background initialization."""

    # Start background cleanup task
    cleanup_task = asyncio.create_task(_periodic_cleanup_task())
    logger.info("Background vector store cleanup task started")

    # Start Ollama initialization in background (non-blocking)
    ollama_task = asyncio.create_task(_initialize_ollama_background())

    try:
        yield  # Server is ready immediately
    finally:
        # Shutdown tasks
        cleanup_task.cancel()
        ollama_task.cancel()

        import contextlib
        
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
            await ollama_task

        logger.info("Background tasks stopped")


async def _initialize_ollama_background():
    """Initialize Ollama adapter in background without blocking startup."""
    try:
        from mcp_the_force.adapters.ollama import startup as ollama_startup

        logger.info("Starting background Ollama initialization...")
        await ollama_startup.initialize()
        logger.info("Ollama adapter initialized successfully in background")

    except ImportError:
        logger.info("Ollama adapter not available - skipping initialization")
    except Exception as e:
        logger.warning(f"Ollama background initialization failed: {e}")
        # Don't raise - server should continue without Ollama


async def _periodic_cleanup_task():
    """Placeholder for existing cleanup task."""
    # Import existing cleanup logic here
    pass
