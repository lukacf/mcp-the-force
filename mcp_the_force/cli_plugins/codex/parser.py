"""
Codex CLI Parser Implementation.

Parses output from OpenAI Codex CLI and formats as clean markdown.
"""

import json
from typing import Any, List, Optional

from mcp_the_force.cli_plugins.base import ParsedCLIResponse


class CodexParser:
    """
    Parses Codex CLI output format and produces clean markdown.

    Expected format: JSONL (multiple JSON lines)
    - {"thread_id": "...", "type": "thread.started"}
    - {"type": "turn.started"}
    - {"type": "item.completed", "item": {"type": "reasoning|command_execution|agent_message", ...}}
    - {"type": "turn.completed"}

    Note: Codex uses thread_id, NOT session_id.

    IMPORTANT: On resume, Codex outputs the entire session transcript.
    This parser extracts only the LAST turn's content to avoid saving
    the full session history to output files.
    """

    def parse(self, output: str) -> ParsedCLIResponse:
        """
        Parse Codex CLI output and return clean markdown from the LAST turn only.

        When resuming a session, Codex outputs all previous turns plus the new one.
        This method extracts only the content from the most recent turn to avoid
        storing duplicate history in output files.

        Args:
            output: Raw Codex CLI output (JSONL - multiple JSON lines)

        Returns:
            ParsedCLIResponse with session_id (from thread_id) and clean markdown
            content from the last turn only
        """
        if not output or not output.strip():
            return ParsedCLIResponse(session_id=None, content="")

        thread_id = None
        # Track content per turn, keyed by turn index
        turns: List[List[str]] = []
        current_turn_content: List[str] = []
        # Content collected outside any turn markers (backward compat)
        unmarked_content: List[str] = []
        in_turn = False
        has_turn_markers = False

        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            try:
                event: Any = json.loads(line)
            except json.JSONDecodeError:
                # Not JSON - might be plain text output
                continue

            if not isinstance(event, dict):
                continue

            event_type = event.get("type", "")

            # Extract thread_id from thread.started event
            if event_type == "thread.started":
                thread_id = event.get("thread_id")

            # Track turn boundaries
            elif event_type == "turn.started":
                # Start a new turn
                has_turn_markers = True
                in_turn = True
                current_turn_content = []

            elif event_type == "turn.completed":
                # End current turn and save it
                has_turn_markers = True
                if current_turn_content:
                    turns.append(current_turn_content)
                current_turn_content = []
                in_turn = False

            # Format item.completed events as markdown
            elif event_type == "item.completed":
                item = event.get("item", {})
                formatted = self._format_item(item)
                if formatted:
                    if in_turn:
                        # Add to current turn
                        current_turn_content.append(formatted)
                    else:
                        # No turn markers - collect for backward compat
                        unmarked_content.append(formatted)

        # Handle incomplete last turn (no turn.completed event)
        if current_turn_content:
            turns.append(current_turn_content)

        # Determine what content to return
        if has_turn_markers and turns:
            # Has turn markers - only return the last turn's content
            last_turn_content = turns[-1]
            content = "\n\n".join(last_turn_content)
        elif unmarked_content:
            # No turn markers (backward compat) - include all unmarked content
            content = "\n\n".join(unmarked_content)
        else:
            content = ""

        # Map thread_id to session_id for unified interface
        return ParsedCLIResponse(session_id=thread_id, content=content)

    def _format_item(self, item: dict) -> Optional[str]:
        """
        Format a single item as markdown.

        Only extracts agent_message content - reasoning and command execution
        are internal process details that shouldn't be in the output.

        Args:
            item: The item dict from item.completed event

        Returns:
            Formatted markdown string or None (only for agent_message items)
        """
        item_type = item.get("type", "")

        # Only extract agent_message - the actual response to the user
        # Reasoning and command_execution are internal process details
        if item_type == "agent_message":
            text = item.get("text", "")
            if text:
                return str(text)

        return None
