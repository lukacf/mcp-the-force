"""
Gemini CLI Parser Implementation.

Parses output from Google Gemini CLI.
"""

import json

from mcp_the_force.cli_plugins.base import ParsedCLIResponse


class GeminiParser:
    """
    Parses Gemini CLI output format.

    Expected format: JSON object
    - {"session_id": "...", "response": "...", "stats": {...}}
    """

    def parse(self, output: str) -> ParsedCLIResponse:
        """
        Parse Gemini CLI output.

        Args:
            output: Raw Gemini CLI output (JSON object)

        Returns:
            ParsedCLIResponse with session_id and content
        """
        if not output or not output.strip():
            return ParsedCLIResponse(session_id=None, content="")

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return ParsedCLIResponse(session_id=None, content="")

        if not isinstance(data, dict):
            return ParsedCLIResponse(session_id=None, content="")

        session_id = data.get("session_id")
        content = data.get("response", "")

        return ParsedCLIResponse(session_id=session_id, content=content)
