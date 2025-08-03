"""Storage of AI assistant conversations in vector store."""

import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import List, Dict, Any, Optional, TypedDict
from xml.etree import ElementTree as ET

from ..config import get_settings
from ..utils.redaction import redact_dict
from .async_config import get_async_history_config

logger = logging.getLogger(__name__)


async def record_conversation(
    session_id: str, tool_name: str, messages: List[Dict[str, Any]], response: str
) -> None:
    """Store conversation summary in vector store after tool call."""
    # History storage is applied universally to all chat tools
    logger.info(
        f"Storing conversation history for tool {tool_name}, session {session_id}"
    )

    try:
        # Import vector store manager to use the abstraction
        from ..vectorstores.manager import vector_store_manager
        from ..vectorstores.protocol import VSFile

        # Get current git state using subprocess (sync, but quick - run in executor if needed)
        loop = asyncio.get_event_loop()
        branch = (
            await loop.run_in_executor(None, _git_command, ["branch", "--show-current"])
            or "main"
        )
        prev_commit_sha = (
            await loop.run_in_executor(None, _git_command, ["rev-parse", "HEAD"])
            or "initial"
        )

        # Get additional git metadata
        # Count commits since main/master
        commits_since_main = 0
        if branch != "main" and branch != "master":
            # Try to get commits ahead of main
            count_str = await loop.run_in_executor(
                None, _git_command, ["rev-list", "--count", "origin/main..HEAD"]
            )
            if count_str and count_str.isdigit():
                commits_since_main = int(count_str)

        # Check if there are uncommitted changes
        status_output = await loop.run_in_executor(
            None, _git_command, ["status", "--porcelain"]
        )
        has_uncommitted_changes = bool(status_output and status_output.strip())

        # Create summary using Gemini Flash (or fallback)
        summary = await create_conversation_summary(messages, response, tool_name)

        # Create document with metadata
        doc: Dict[str, Any] = {
            "content": summary,
            "metadata": {
                "type": "conversation",
                "session_id": session_id,
                "tool": tool_name,
                "branch": branch,
                "prev_commit_sha": prev_commit_sha,
                "commits_since_main": commits_since_main,
                "has_uncommitted_changes": has_uncommitted_changes,
                "timestamp": int(time.time()),
                "datetime": datetime.now(timezone.utc).isoformat(),
                "message_count": len(messages),
                "response_length": len(response),
            },
        }

        # Extract timestamp for filename (before redaction to ensure type safety)
        timestamp = doc["metadata"]["timestamp"]

        # Redact secrets before storage
        doc = redact_dict(doc)

        # Get active store and upload
        config = get_async_history_config()
        logger.debug("[HISTORY] Getting active conversation store...")
        store_id = await config.get_active_conversation_store()
        logger.debug(f"[HISTORY] Got store ID: {store_id}")

        # Create temporary file in thread pool to avoid blocking
        tmp_path = await loop.run_in_executor(None, _create_temp_file, doc, session_id)
        logger.debug(f"[HISTORY] Created temp file: {tmp_path}")

        try:
            # Upload to vector store using the abstraction
            with open(tmp_path, "r") as f:
                content = f.read()

            # Create VSFile
            vs_file = VSFile(
                path=f"conversations/{session_id}_{timestamp}.json",
                content=content,
                metadata={
                    "type": "conversation",
                    "session_id": session_id,
                    "tool": tool_name,
                },
            )

            # Get the vector store and add the file
            client = vector_store_manager._get_client(vector_store_manager.provider)
            store = await client.get(store_id)
            await store.add_files([vs_file])

            # Increment count
            config.increment_conversation_count()

        finally:
            # Clean up temp file in thread pool
            await loop.run_in_executor(
                None, Path(tmp_path).unlink, True
            )  # missing_ok=True

    except Exception:
        # Log error but don't fail the tool call
        logger.exception("Failed to store conversation history")


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
                # Handle both string content and list content (newer format)
                if isinstance(raw_content, list):
                    # Extract text from content parts
                    text_parts = []
                    for part in raw_content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                    raw_content = "\n".join(text_parts)
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
        from ..adapters.registry import get_adapter_class
        from ..config import get_settings

        settings = get_settings()

        # Sanitize the response to avoid LiteLLM misinterpreting tool call patterns
        sanitized_response = response[: settings.history_summary_char_limit]
        # Remove any JSON-like structures that might confuse LiteLLM
        # This is a workaround for LiteLLM potentially misinterpreting text as actual tool calls
        import re

        # Remove or escape patterns that look like tool call JSON
        sanitized_response = re.sub(
            r'"tool_calls?"', '"tool-calls"', sanitized_response
        )
        sanitized_response = re.sub(
            r'"role":\s*"tool"', '"role": "tool-response"', sanitized_response
        )
        # Remove any JSON blocks that might contain tool call structures
        sanitized_response = re.sub(
            r'\{[^}]*"tool_call[^}]*\}',
            "[tool call details removed]",
            sanitized_response,
        )

        # Build a clean representation of the conversation
        conversation_text = f"""
## User Request
Instructions: {user_components["instructions"]}
Output Format: {user_components["output_format"]}
Context Files: {len(user_components["context_files"])} files provided
Vector Store Attachments: {"Yes" if user_components["has_attachments"] else "No"}

## Assistant Response ({tool_name})
{sanitized_response}
"""

        # Use Gemini Flash to create summary
        summarization_prompt = f"""You are generating a knowledge base entry for Claude's project history.
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
        try:
            adapter_cls = get_adapter_class("google")
            adapter = adapter_cls("gemini-2.5-flash")
        except Exception as e:
            logger.warning(f"Failed to get Vertex adapter for summarization: {e}")
            # Fall back to structured summary
            return _create_fallback_summary(user_components, response, tool_name)

        # Create minimal params for MCPAdapter protocol
        from types import SimpleNamespace
        from ..adapters.protocol import CallContext
        from ..adapters.tool_dispatcher import ToolDispatcher

        # Use a unique session ID to avoid contamination from previous runs
        import uuid

        unique_session_id = f"history-summarization-{uuid.uuid4().hex[:8]}"

        params = SimpleNamespace(
            temperature=0.3,
            disable_history_search=True,  # No tools needed for summarization
        )
        ctx = CallContext(
            session_id=unique_session_id,
            project="history-system",
            tool="gemini25_flash",
            vector_store_ids=None,
        )
        tool_dispatcher = ToolDispatcher(vector_store_ids=None)

        result = await adapter.generate(
            prompt=summarization_prompt,
            params=params,
            ctx=ctx,
            tool_dispatcher=tool_dispatcher,
        )

        # Extract content from result
        summary = result.get("content", "") if isinstance(result, dict) else str(result)

        # Clean up the temporary session to avoid database bloat
        from ..unified_session_cache import UnifiedSessionCache

        await UnifiedSessionCache.delete_session(
            project="history-system",
            tool="gemini25_flash",
            session_id=unique_session_id,
        )
        logger.debug(f"Cleaned up temporary summarization session: {unique_session_id}")

        final_summary = summary

        # Add metadata header
        return f"""## AI Consultation Session
**Tool**: {tool_name}
**Date**: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

{final_summary}
"""

    except Exception as e:
        logger.warning(f"Failed to use Gemini Flash for summarization: {e}")
        # Fall back to structured summary
        return _create_fallback_summary(user_components, response, tool_name)


def _create_fallback_summary(
    user_components: MessageComponents, response: str, tool_name: str
) -> str:
    """Create a structured summary when Gemini Flash is unavailable."""

    settings = get_settings()

    # Include actual response content in fallback
    response_preview = response[: settings.history_summary_char_limit]

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


def _create_temp_file(doc: Dict[str, Any], session_id: str) -> str:
    """Synchronous helper to create temp file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=f"_conv_{session_id}.json", delete=False
    ) as tmp_file:
        json.dump(doc, tmp_file, indent=2)
        return tmp_file.name


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
