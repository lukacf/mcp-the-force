"""Storage of AI assistant conversations in vector store."""

import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
import tempfile
from typing import List, Dict, Any, Optional

from ..utils.vector_store import get_client
from ..utils.redaction import redact_dict
from .config import get_memory_config

logger = logging.getLogger(__name__)


async def store_conversation_memory(
    session_id: str, tool_name: str, messages: List[Dict[str, Any]], response: str
) -> None:
    """Store conversation summary in vector store after tool call.

    Args:
        session_id: Current session identifier
        tool_name: Name of the tool called (e.g., chat_with_o3)
        messages: Conversation messages
        response: Tool response
    """
    # Check if tool writes to memory using capability flag
    from ..tools.registry import get_tool

    tool_metadata = get_tool(tool_name)
    if not tool_metadata or not tool_metadata.capabilities.get("writes_memory"):
        return

    try:
        # Get current git state using subprocess
        branch = _git_command(["branch", "--show-current"]) or "main"
        prev_commit_sha = _git_command(["rev-parse", "HEAD"]) or "initial"

        # Create summary (in production, would use Gemini Flash)
        summary = create_conversation_summary(messages, response, tool_name)

        # Create document with metadata
        doc = {
            "content": summary,
            "messages": messages,  # Store messages for better context
            "response": response,
            "metadata": {
                "type": "conversation",
                "session_id": session_id,
                "tool": tool_name,
                "branch": branch,
                "prev_commit_sha": prev_commit_sha,
                "timestamp": int(time.time()),
                "datetime": datetime.utcnow().isoformat(),
            },
        }
        
        # Redact secrets before storage
        doc = redact_dict(doc)

        # Get active store and upload
        config = get_memory_config()
        store_id = config.get_active_conversation_store()

        # Create temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f"_conv_{session_id}.json", delete=False
        ) as tmp_file:
            json.dump(doc, tmp_file, indent=2)
            tmp_path = tmp_file.name

        try:
            # Upload to vector store
            client = get_client()
            with open(tmp_path, "rb") as f:
                client.vector_stores.files.upload_and_poll(
                    vector_store_id=store_id, file=f
                )

            # Increment count
            config.increment_conversation_count()

        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)

    except Exception:
        # Log error but don't fail the tool call
        logger.exception("Failed to store conversation memory")


def create_conversation_summary(
    messages: List[Dict[str, Any]], response: str, tool_name: str
) -> str:
    """Create a summary of the conversation.

    In production, this would use Gemini Flash for summarization.
    For now, we create a structured summary.
    """
    # Extract key information
    user_query = ""
    if messages:
        # Find the main user query (usually the instructions)
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                from ..config import get_settings

                settings = get_settings()
                user_query = msg.get("content", "")[
                    : settings.memory_summary_char_limit
                ]
                break

    # Create structured summary
    summary = f"""## AI Consultation Session

**Tool**: {tool_name}
**Date**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

### User Query
{user_query or "No query captured"}

### Assistant Response Summary
The assistant provided analysis and recommendations regarding the query.

### Key Points
- Consultation completed successfully
- Response provided by {tool_name}
- Full context available in session

### Technical Context
This consultation may have influenced subsequent code changes.
Check commits with matching session_id for implementation details.
"""

    return summary


def _git_command(args: List[str]) -> Optional[str]:
    """Execute git command safely and return output."""
    try:
        result = subprocess.run(
            ["git"] + args, capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.debug(f"Git command failed: {' '.join(args)} - {result.stderr}")
            return None
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.debug(f"Git command error: {e}")
        return None
