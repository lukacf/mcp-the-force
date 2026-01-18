"""
CLI output parsers.

Each CLI has a different output format:
- Claude: JSON array with init and result events
- Gemini: JSON object with session_id and response
- Codex: JSONL with thread_id (not session_id)
"""

from mcp_the_force.cli_agents.parsers.base import ParsedCLIResponse
from mcp_the_force.cli_agents.parsers.claude import ClaudeParser
from mcp_the_force.cli_agents.parsers.gemini import GeminiParser
from mcp_the_force.cli_agents.parsers.codex import CodexParser

__all__ = [
    "ParsedCLIResponse",
    "ClaudeParser",
    "GeminiParser",
    "CodexParser",
]
