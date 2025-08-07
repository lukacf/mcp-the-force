"""Startup initialization for Ollama adapter."""

import logging

from ...config import get_settings
from . import blueprint_generator

logger = logging.getLogger(__name__)


async def initialize():
    """Initialize Ollama adapter on server startup."""
    settings = get_settings()

    if not settings.ollama.enabled:
        logger.info("Ollama integration disabled")
        return

    try:
        await blueprint_generator.initialize()
        logger.info("Ollama adapter initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Ollama adapter: {e}", exc_info=True)


def shutdown():
    """Cleanup on server shutdown."""
    try:
        blueprint_generator.shutdown()
        logger.info("Ollama adapter shutdown complete")
    except Exception as e:
        logger.error(f"Error during Ollama adapter shutdown: {e}", exc_info=True)
