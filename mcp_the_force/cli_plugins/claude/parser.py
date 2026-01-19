"""
Claude CLI Parser Implementation.

Parses output from Anthropic Claude Code CLI.
"""

import json
from typing import Any, List

from mcp_the_force.cli_plugins.base import ParsedCLIResponse


class ClaudeParser:
    """
    Parses Claude CLI output format.

    Expected format: JSON array with events
    - {"type": "system", "subtype": "init", "session_id": "..."}
    - {"type": "result", "subtype": "success", "result": "..."}
    """

    def parse(self, output: str) -> ParsedCLIResponse:
        """
        Parse Claude CLI output.

        Args:
            output: Raw Claude CLI output (JSON from --output-format=json)

        Returns:
            ParsedCLIResponse with session_id and content

        Handles two formats:
        - Single JSON object: {"type": "result", "result": "...", "session_id": "..."}
        - JSON array: [{"type": "system", ...}, {"type": "result", ...}]
        """
        if not output or not output.strip():
            return ParsedCLIResponse(session_id=None, content="")

        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            # Fallback: treat as plain text if JSON parsing fails
            return ParsedCLIResponse(session_id=None, content=output.strip())

        # Handle single object vs array
        if isinstance(parsed, dict):
            events: List[Any] = [parsed]
        elif isinstance(parsed, list):
            events = parsed
        else:
            # Unexpected type, treat as plain text
            return ParsedCLIResponse(session_id=None, content=output.strip())

        session_id = None
        content = ""

        for event in events:
            if not isinstance(event, dict):
                continue

            # Extract session_id from init event OR result event
            if event.get("type") == "system" and event.get("subtype") == "init":
                session_id = event.get("session_id")
            elif event.get("type") == "result" and event.get("session_id"):
                # Result events also include session_id
                session_id = event.get("session_id")

            # Extract content from result event
            if event.get("type") == "result":
                content = event.get("result", "")

        return ParsedCLIResponse(session_id=session_id, content=content)
