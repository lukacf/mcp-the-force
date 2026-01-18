"""
Base types for CLI output parsing.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ParsedCLIResponse:
    """
    Unified response type from all CLI parsers.

    Normalizes differences between CLI output formats into a common structure.
    """

    session_id: Optional[str]
    """CLI-native session identifier (session_id for Claude/Gemini, thread_id for Codex)"""

    content: str
    """Extracted response content"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Optional metadata from the CLI output"""
