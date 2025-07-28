"""Safe wrapper for memory storage operations that prevents response conflicts."""

import logging
from typing import List, Dict, Any

from ..memory import store_conversation_memory
from ..config import get_settings

logger = logging.getLogger(__name__)


async def safe_store_conversation_memory(
    session_id: str,
    tool_name: str,
    messages: List[Dict[str, Any]],
    response: str,
) -> None:
    """
    Wrapper for store_conversation_memory that swallows all exceptions,
    making it safe to run in a fire-and-forget background task.
    """
    logger.info(
        f"[MEMORY] safe_store_conversation_memory called for {tool_name}, session={session_id}"
    )

    # Skip memory storage in mock adapter mode (for tests)
    settings = get_settings()
    if settings.dev.adapter_mock:
        logger.debug("[MEMORY] Skipping memory storage in mock adapter mode")
        return

    try:
        await store_conversation_memory(session_id, tool_name, messages, response)
        logger.debug(
            f"[MEMORY] Successfully stored conversation memory for {tool_name}"
        )
    except Exception as e:
        logger.warning(
            f"Failed to store conversation memory in background task: {e}",
            exc_info=True,
        )
