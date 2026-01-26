"""CLI Output Cleaner.

Transforms raw CLI output (JSONL, etc.) into clean markdown.
Handles Codex CLI's JSONL format and plain text from other CLIs.
"""

import json
import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from ..utils.token_counter import count_tokens

logger = logging.getLogger(__name__)

# Default threshold for "large" output (10k tokens)
DEFAULT_TOKEN_THRESHOLD = 10_000


@dataclass
class CleanedOutput:
    """Result of cleaning CLI output."""

    markdown: str
    token_count: int
    exceeds_threshold: bool
    thread_id: Optional[str] = None


class OutputCleaner:
    """
    Cleans raw CLI output into readable markdown.

    Handles:
    - Codex CLI JSONL format (reasoning, commands, agent messages)
    - Plain text passthrough for other CLIs
    - Token counting for large output detection
    """

    def __init__(self, token_threshold: int = DEFAULT_TOKEN_THRESHOLD):
        """
        Initialize the cleaner.

        Args:
            token_threshold: Token count above which output is considered "large"
        """
        self._token_threshold = token_threshold

    def clean(self, raw_output: str) -> CleanedOutput:
        """
        Clean raw CLI output into markdown.

        Args:
            raw_output: Raw output from CLI (JSONL or plain text)

        Returns:
            CleanedOutput with markdown, token count, and metadata
        """
        if not raw_output or not raw_output.strip():
            return CleanedOutput(
                markdown="",
                token_count=0,
                exceeds_threshold=False,
                thread_id=None,
            )

        # Try to parse as JSONL (Codex format)
        jsonl_result = self._try_parse_jsonl(raw_output)

        if jsonl_result["is_jsonl"]:
            markdown = self._format_jsonl_as_markdown(jsonl_result)
            thread_id = jsonl_result.get("thread_id")
        else:
            # Plain text passthrough
            markdown = raw_output.strip()
            thread_id = None

        # Count tokens
        token_count = count_tokens(markdown)
        exceeds_threshold = token_count > self._token_threshold

        return CleanedOutput(
            markdown=markdown,
            token_count=token_count,
            exceeds_threshold=exceeds_threshold,
            thread_id=thread_id,
        )

    def _try_parse_jsonl(self, raw_output: str) -> dict:
        """
        Try to parse output as JSONL (Codex format).

        Returns dict with:
        - is_jsonl: True if at least some valid JSONL was found
        - thread_id: Thread ID if found
        - events: List of parsed events
        - plain_lines: Lines that weren't valid JSON
        """
        result: dict[str, Any] = {
            "is_jsonl": False,
            "thread_id": None,
            "events": [],
            "plain_lines": [],
        }

        json_count = 0
        plain_count = 0

        for line in raw_output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    json_count += 1
                    result["events"].append(event)

                    # Extract thread_id
                    if event.get("type") == "thread.started":
                        result["thread_id"] = event.get("thread_id")
                else:
                    plain_count += 1
                    result["plain_lines"].append(line)
            except json.JSONDecodeError:
                plain_count += 1
                result["plain_lines"].append(line)

        # Consider it JSONL if majority of non-empty lines are valid JSON
        result["is_jsonl"] = json_count > 0 and json_count >= plain_count

        return result

    def _format_jsonl_as_markdown(self, jsonl_result: dict) -> str:
        """
        Format parsed JSONL events as clean markdown from the LAST turn only.

        When resuming a session, Codex outputs all previous turns plus the new one.
        This method extracts only the content from the most recent turn to avoid
        storing duplicate history in output files.

        Args:
            jsonl_result: Parsed JSONL result from _try_parse_jsonl

        Returns:
            Clean markdown string from the last turn only
        """
        # Track content per turn
        turns: List[List[str]] = []
        current_turn_content: List[str] = []
        # Content collected outside any turn markers (backward compat)
        unmarked_content: List[str] = []
        in_turn = False
        has_turn_markers = False

        for event in jsonl_result["events"]:
            event_type = event.get("type", "")

            # Track turn boundaries
            if event_type == "turn.started":
                has_turn_markers = True
                in_turn = True
                current_turn_content = []
            elif event_type == "turn.completed":
                has_turn_markers = True
                if current_turn_content:
                    turns.append(current_turn_content)
                current_turn_content = []
                in_turn = False
            elif event_type == "item.completed":
                item = event.get("item", {})
                section = self._format_item(item)
                if section:
                    if in_turn:
                        current_turn_content.append(section)
                    else:
                        # No turn markers - collect for backward compat
                        unmarked_content.append(section)

        # Handle incomplete last turn
        if current_turn_content:
            turns.append(current_turn_content)

        # Determine what content to return
        if has_turn_markers and turns:
            # Has turn markers - only return the last turn's content
            sections = turns[-1]
        elif unmarked_content:
            # No turn markers (backward compat) - include all unmarked content
            sections = unmarked_content
        else:
            sections = []

        # Include any plain lines that weren't JSON
        if jsonl_result["plain_lines"]:
            plain_text = "\n".join(jsonl_result["plain_lines"])
            if plain_text.strip():
                sections.append(plain_text)

        return "\n\n".join(sections)

    def _format_item(self, item: dict) -> Optional[str]:
        """
        Format a single item from item.completed event.

        Only extracts agent_message content - reasoning and command execution
        are internal process details that shouldn't be in the output.

        Args:
            item: The item dict from the event

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


class OutputFileHandler:
    """
    Handles writing large outputs to files and creating summaries with links.

    Used when CLI output exceeds the token threshold to avoid filling context.
    """

    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize the handler.

        Args:
            output_dir: Directory to write output files. Defaults to system temp.
        """
        if output_dir:
            self._output_dir = output_dir
        else:
            self._output_dir = tempfile.gettempdir()

        # Ensure directory exists
        Path(self._output_dir).mkdir(parents=True, exist_ok=True)

    @property
    def output_dir(self) -> str:
        """Return the output directory path."""
        return self._output_dir

    def save_to_file(self, markdown: str, session_id: str) -> Path:
        """
        Save markdown content to a file.

        Args:
            markdown: The markdown content to save
            session_id: Session ID for filename

        Returns:
            Path to the saved file
        """
        # Create a unique filename with session ID and timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_session = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in session_id
        )
        filename = f"work_with-{safe_session}-{timestamp}.md"

        file_path = Path(self._output_dir) / filename
        file_path.write_text(markdown, encoding="utf-8")

        logger.info(f"Saved large output to: {file_path}")
        return file_path

    def format_summary_with_link(self, summary: str, file_path: Path) -> str:
        """
        Format a summary with a link to the full output file.

        Args:
            summary: The summarized content
            file_path: Path to the full output file

        Returns:
            Formatted string with summary and file link
        """
        return f"""{summary}

---
📄 **Full output details saved to:** `{file_path}`"""
