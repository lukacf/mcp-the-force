"""
ClaudeParser: Parse Claude CLI JSON array output.

Claude outputs a JSON array with events:
- {"type": "system", "subtype": "init", "session_id": "..."}
- {"type": "result", "subtype": "success", "result": "..."}
"""

import json
from typing import Any, List

from mcp_the_force.cli_agents.parsers.base import ParsedCLIResponse


class ClaudeParser:
    """
    Parses Claude CLI output format.

    Expected format: JSON array with init event containing session_id
    and result event containing the response.
    """

    def parse(self, output: str) -> ParsedCLIResponse:
        """
        Parse Claude CLI output.

        Args:
            output: Raw Claude CLI output (JSON array)

        Returns:
            ParsedCLIResponse with session_id and content
        """
        if not output or not output.strip():
            return ParsedCLIResponse(session_id=None, content="")

        try:
            events: List[Any] = json.loads(output)
        except json.JSONDecodeError:
            return ParsedCLIResponse(session_id=None, content="")

        session_id = None
        content = ""

        for event in events:
            if not isinstance(event, dict):
                continue

            # Extract session_id from init event
            if event.get("type") == "system" and event.get("subtype") == "init":
                session_id = event.get("session_id")

            # Extract content from result event
            if event.get("type") == "result":
                content = event.get("result", "")

        return ParsedCLIResponse(session_id=session_id, content=content)
