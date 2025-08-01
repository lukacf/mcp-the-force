"""Safe wrapper for history storage operations that prevents response conflicts."""

import logging
from typing import List, Dict, Any

from ..history import record_conversation
from ..config import get_settings

logger = logging.getLogger(__name__)


async def safe_record_conversation(
    session_id: str,
    tool_name: str,
    messages: List[Dict[str, Any]],
    response: str,
) -> None:
    """
    Wrapper for record_conversation that swallows all exceptions,
    making it safe to run in a fire-and-forget background task.
    """
    logger.info(
        f"[HISTORY] safe_record_conversation called for {tool_name}, session={session_id}"
    )

    # Skip history storage in mock adapter mode (for tests)
    settings = get_settings()
    if settings.dev.adapter_mock:
        logger.debug("[HISTORY] Skipping history storage in mock adapter mode")
        return

    try:
        await record_conversation(session_id, tool_name, messages, response)
        logger.debug(
            f"[HISTORY] Successfully stored conversation history for {tool_name}"
        )
    except Exception as e:
        logger.warning(
            f"Failed to store conversation history in background task: {e}",
            exc_info=True,
        )
