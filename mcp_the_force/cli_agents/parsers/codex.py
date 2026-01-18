"""
CodexParser: Parse Codex CLI JSONL output.

Codex outputs JSONL (multiple JSON lines):
{"thread_id": "...", "type": "thread.started"}
{"type": "turn.started"}
{"type": "item.completed", "content": "..."}
{"type": "turn.completed"}

Note: Codex uses thread_id, NOT session_id.
"""

import json
from typing import List

from mcp_the_force.cli_agents.parsers.base import ParsedCLIResponse


class CodexParser:
    """
    Parses Codex CLI output format.

    Expected format: JSONL with thread_id in thread.started event
    and content aggregated from item.completed events.
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
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(event, dict):
                continue

            # Extract thread_id from thread.started event
            if event.get("type") == "thread.started":
                thread_id = event.get("thread_id")

            # Aggregate content from item.completed events
            if event.get("type") == "item.completed":
                item_content = event.get("content", "")
                if item_content:
                    content_parts.append(item_content)

        # Join all content parts
        content = "\n".join(content_parts)

        # Map thread_id to session_id for unified interface
        return ParsedCLIResponse(session_id=thread_id, content=content)
