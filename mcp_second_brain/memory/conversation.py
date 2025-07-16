"""Storage of AI assistant conversations in vector store."""

import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import List, Dict, Any, Optional, TypedDict
from xml.etree import ElementTree as ET

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

        # Create summary using Gemini Flash (or fallback)
        summary = await create_conversation_summary(messages, response, tool_name)

        # Create document with metadata - only store summary, not raw messages
        doc = {
            "content": summary,
            "metadata": {
                "type": "conversation",
                "session_id": session_id,
                "tool": tool_name,
                "branch": branch,
                "prev_commit_sha": prev_commit_sha,
                "timestamp": int(time.time()),
                "datetime": datetime.now(timezone.utc).isoformat(),
                "message_count": len(messages),
                "response_length": len(response),
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
            # Upload to vector store (fire-and-forget to prevent hangs)
            client = get_client()
            with open(tmp_path, "rb") as f:
                # First upload file to OpenAI
                file_obj = client.files.create(file=f, purpose="assistants")
                # Then add to vector store
                client.vector_stores.files.create(
                    vector_store_id=store_id, file_id=file_obj.id
                )

            # Increment count
            config.increment_conversation_count()

        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)

    except Exception:
        # Log error but don't fail the tool call
        logger.exception("Failed to store conversation memory")


class MessageComponents(TypedDict):
    """Type definition for extracted message components."""

    instructions: str
    output_format: str
    context_files: List[str]
    has_attachments: bool


def _extract_message_components(raw_msg: str) -> MessageComponents:
    """Extract components from a Task prompt.

    Returns dict with:
    - instructions: The user's actual instructions
    - output_format: The requested output format
    - context_files: List of file paths (not content)
    - has_attachments: Bool indicating if vector store attachments exist
    """
    result: MessageComponents = {
        "instructions": "",
        "output_format": "",
        "context_files": [],
        "has_attachments": False,
    }

    try:
        # Try to parse as XML
        root = ET.fromstring(raw_msg)

        # Extract instructions
        instructions = root.findtext(".//Instructions")
        if instructions:
            result["instructions"] = instructions.strip()

        # Extract output format
        output_format = root.findtext(".//OutputFormat")
        if output_format:
            result["output_format"] = output_format.strip()

        # Extract file paths (not content)
        context = root.find(".//CONTEXT")
        if context is not None:
            for file_elem in context.findall(".//file"):
                path = file_elem.get("path")
                if path:
                    result["context_files"].append(path)

    except ET.ParseError:
        # Not valid XML, fall back to simple extraction
        # Try to at least get the instructions
        context_idx = raw_msg.find("<CONTEXT>")
        if context_idx != -1:
            result["instructions"] = raw_msg[:context_idx].strip()
        else:
            result["instructions"] = raw_msg.strip()

    # Check for vector store attachments
    if "additional information accessible through the file search tool" in raw_msg:
        result["has_attachments"] = True

    return result


async def create_conversation_summary(
    messages: List[Dict[str, Any]], response: str, tool_name: str
) -> str:
    """Create a summary of the conversation using Gemini Flash.

    Falls back to structured summary if Gemini is unavailable.
    """
    # Extract components from user message
    user_components = None
    if messages:
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                raw_content = msg.get("content", "")
                user_components = _extract_message_components(raw_content)
                break

    if not user_components:
        user_components = {
            "instructions": "No query captured",
            "output_format": "",
            "context_files": [],
            "has_attachments": False,
        }

    # Try to use Gemini Flash for summarization
    try:
        from ..adapters import get_adapter
        from ..config import get_settings

        settings = get_settings()

        # Build a clean representation of the conversation
        conversation_text = f"""
## User Request
Instructions: {user_components["instructions"]}
Output Format: {user_components["output_format"]}
Context Files: {len(user_components["context_files"])} files provided
Vector Store Attachments: {"Yes" if user_components["has_attachments"] else "No"}

## Assistant Response ({tool_name})
{response[: settings.memory_summary_char_limit]}
"""

        # Use Gemini Flash to create summary
        summarization_prompt = f"""You are generating a knowledge base entry for Claude's project memory.
Summaries must be dense with technical detail so future searches can locate this session.
Focus on:
1. The user's explicit request or question.
2. Key findings or analysis produced by the tool ({tool_name}).
3. Decisions or concrete recommendations, including file names or error messages.
4. Any identifiers or values that uniquely describe the problem and solution.

Bad summary example:
- "We discussed a bug fix."

Good summary example:
- "User asked how to fix the 2024-05-12 JWT expiry bug in auth.py. {tool_name} traced
  the issue to `validate_token` ignoring the `leeway` parameter and recommended adding
  `jwt.decode(..., leeway=30)` at line 42."

Keep the final summary under 1000 words and preserve all specific tokens exactly.

Conversation to summarize:
{conversation_text}
"""

        # Use the central adapter factory instead of direct instantiation
        adapter, error = get_adapter("vertex", "gemini-2.5-flash")
        if not adapter:
            logger.warning(f"Failed to get Vertex adapter for summarization: {error}")
            # Fall back to structured summary
            return _create_fallback_summary(user_components, response, tool_name)

        summary = await adapter.generate(
            prompt=summarization_prompt, vector_store_ids=None, temperature=0.3
        )

        # Add metadata header
        return f"""## AI Consultation Session
**Tool**: {tool_name}
**Date**: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

{summary}
"""

    except Exception as e:
        logger.warning(f"Failed to use Gemini Flash for summarization: {e}")
        # Fall back to structured summary
        return _create_fallback_summary(user_components, response, tool_name)


def _create_fallback_summary(
    user_components: MessageComponents, response: str, tool_name: str
) -> str:
    """Create a structured summary when Gemini Flash is unavailable."""
    from ..config import get_settings

    settings = get_settings()

    # Include actual response content in fallback
    response_preview = response[: settings.memory_summary_char_limit]

    summary = f"""## AI Consultation Session

**Tool**: {tool_name}
**Date**: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

### User Query
{user_components["instructions"]}

### Output Format
{user_components["output_format"] or "Not specified"}

### Context
- Files provided: {len(user_components["context_files"])}
- Vector store attachments: {"Yes" if user_components["has_attachments"] else "No"}

### Assistant Response
{response_preview}

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
