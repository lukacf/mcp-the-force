"""
Codex CLI Parser Implementation.

Parses output from OpenAI Codex CLI.
"""

import json
from typing import Any, List

from mcp_the_force.cli_plugins.base import ParsedCLIResponse


class CodexParser:
    """
    Parses Codex CLI output format.

    Expected format: JSONL (multiple JSON lines)
    - {"thread_id": "...", "type": "thread.started"}
    - {"type": "turn.started"}
    - {"type": "item.completed", "content": "..."}
    - {"type": "turn.completed"}

    Note: Codex uses thread_id, NOT session_id.
    """

    def parse(self, output: str) -> ParsedCLIResponse:
        """
        Parse Codex CLI output.

        Args:
            output: Raw Codex CLI output (JSONL - multiple JSON lines)

        Returns:
            ParsedCLIResponse with session_id (from thread_id) and content
        """
        if not output or not output.strip():
            return ParsedCLIResponse(session_id=None, content="")

        thread_id = None
        content_parts: List[str] = []

        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            try:
                event: Any = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(event, dict):
                continue

            # Extract thread_id from thread.started event
            if event.get("type") == "thread.started":
                thread_id = event.get("thread_id")

            # Aggregate content from item.completed events
            # Codex output format: {"type":"item.completed","item":{"id":"...","type":"agent_message","text":"..."}}
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                item_type = item.get("type", "")
                # Only include agent_message content, not reasoning/thinking
                if item_type == "agent_message":
                    item_content = item.get("text", "")
                    if item_content:
                        content_parts.append(item_content)

        # Join all content parts
        content = "\n".join(content_parts)

        # Map thread_id to session_id for unified interface
        return ParsedCLIResponse(session_id=thread_id, content=content)
