"""
TranscriptTailer: Utility for reading and parsing CLI session transcripts.

Supports different transcript formats from Codex (JSONL), Claude (JSONL),
and Gemini (JSON) CLIs.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

TranscriptFormat = Literal["codex", "claude", "gemini"]


class TranscriptTailer:
    """
    Utility for reading and parsing CLI session transcripts.

    Handles different transcript formats:
    - Codex: JSONL with thread events, agent_message, function_call
    - Claude: JSONL with user/assistant messages
    - Gemini: JSON with messages array
    """

    def __init__(self, format: TranscriptFormat):
        """Initialize tailer with specific format."""
        self.format = format

    @classmethod
    def from_file(cls, path: Path) -> "TranscriptTailer":
        """
        Create a tailer with auto-detected format based on file content.

        Args:
            path: Path to transcript file

        Returns:
            TranscriptTailer with detected format
        """
        format = cls._detect_format(path)
        return cls(format=format)

    @classmethod
    def _detect_format(cls, path: Path) -> TranscriptFormat:
        """Detect transcript format from file content."""
        try:
            with open(path, "r") as f:
                first_line = f.readline().strip()

            if not first_line:
                return "codex"  # Default

            # Try to parse as JSON
            try:
                data = json.loads(first_line)

                # Check for Codex indicators
                if isinstance(data, dict):
                    if "thread_id" in data or data.get("type") == "thread.started":
                        return "codex"
                    if data.get("type") in ("user", "assistant"):
                        return "claude"
                    if "messages" in data:
                        return "gemini"

                # If it's a JSON object on its own line, likely JSONL (Codex/Claude)
                if isinstance(data, dict):
                    # Check for Codex-specific fields
                    if "item" in data or "payload" in data:
                        return "codex"
                    # Check for Claude-specific fields
                    if "message" in data:
                        return "claude"

            except json.JSONDecodeError:
                pass

            # Check if file is a complete JSON object (Gemini)
            with open(path, "r") as f:
                content = f.read()
            try:
                full_data = json.loads(content)
                if isinstance(full_data, dict) and "messages" in full_data:
                    return "gemini"
            except json.JSONDecodeError:
                pass

        except (OSError, IOError):
            pass

        return "codex"  # Default

    def tail(self, path: Path, lines: int = 50) -> List[Dict[str, Any]]:
        """
        Read and parse the last N relevant entries from a transcript.

        Args:
            path: Path to transcript file
            lines: Maximum number of entries to return

        Returns:
            List of parsed entries with 'type', 'text', and optional metadata
        """
        if self.format == "gemini":
            return self._tail_gemini(path, lines)
        elif self.format == "claude":
            return self._tail_claude(path, lines)
        else:
            return self._tail_codex(path, lines)

    def _tail_codex(self, path: Path, lines: int) -> List[Dict[str, Any]]:
        """Parse Codex JSONL transcript."""
        entries = []

        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entry = self._parse_codex_entry(data)
                        if entry:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except (OSError, IOError):
            pass

        # Return last N entries
        return entries[-lines:] if len(entries) > lines else entries

    def _parse_codex_entry(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single Codex JSONL entry."""
        timestamp = data.get("timestamp")

        # Agent message (legacy format)
        if data.get("type") == "item.completed":
            item = data.get("item", {})
            if item.get("type") == "agent_message":
                return {
                    "type": "message",
                    "text": item.get("text", ""),
                    "timestamp": timestamp,
                }

        # Response item (current format)
        if data.get("type") == "response_item":
            payload = data.get("payload", {})
            payload_type = payload.get("type")

            # Message (current format)
            if payload_type == "message":
                # Extract text from content array
                content = payload.get("content", [])
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "output_text":
                        text_parts.append(item.get("text", ""))
                if text_parts:
                    return {
                        "type": "message",
                        "text": "\n".join(text_parts),
                        "timestamp": timestamp,
                    }

            # Reasoning (current format) - uses summary array, content is encrypted
            if payload_type == "reasoning":
                summary = payload.get("summary", [])
                text_parts = []
                for item in summary:
                    if isinstance(item, dict) and item.get("type") == "summary_text":
                        text_parts.append(item.get("text", ""))
                if text_parts:
                    return {
                        "type": "reasoning",
                        "text": "\n".join(text_parts),
                        "timestamp": timestamp,
                    }

            # Function call (tool use)
            if payload_type == "function_call":
                return {
                    "type": "tool_call",
                    "name": payload.get("name", ""),
                    "arguments": payload.get("arguments", ""),
                    "timestamp": timestamp,
                }
            if payload_type == "function_call_output":
                return {
                    "type": "tool_output",
                    "output": payload.get("output", ""),
                    "timestamp": timestamp,
                }

        # Reasoning/thinking (legacy format)
        if data.get("type") == "event_msg":
            payload = data.get("payload", {})
            if payload.get("type") == "agent_reasoning":
                return {
                    "type": "reasoning",
                    "text": payload.get("text", ""),
                    "timestamp": timestamp,
                }

        return None

    def _tail_claude(self, path: Path, lines: int) -> List[Dict[str, Any]]:
        """Parse Claude JSONL transcript."""
        entries = []

        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entry = self._parse_claude_entry(data)
                        if entry:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except (OSError, IOError):
            pass

        return entries[-lines:] if len(entries) > lines else entries

    def _parse_claude_entry(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single Claude JSONL entry."""
        entry_type = data.get("type")

        # Assistant message
        if entry_type == "assistant":
            message = data.get("message", {})
            content = message.get("content", "")

            # Handle content that might be a list (tool use)
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        return {
                            "type": "tool_call",
                            "name": item.get("name", ""),
                            "input": item.get("input", {}),
                        }
                # Extract text from content list
                text_parts = [
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                content = "\n".join(text_parts)

            if content:
                return {"type": "message", "text": content}

        # Tool result
        if entry_type == "tool_result":
            return {
                "type": "tool_output",
                "output": data.get("content", ""),
            }

        return None

    def _tail_gemini(self, path: Path, lines: int) -> List[Dict[str, Any]]:
        """Parse Gemini JSON transcript."""
        entries = []

        try:
            with open(path, "r") as f:
                data = json.load(f)

            messages = data.get("messages", [])
            for msg in messages:
                entry = self._parse_gemini_entry(msg)
                if entry:
                    entries.append(entry)

        except (OSError, IOError, json.JSONDecodeError):
            pass

        return entries[-lines:] if len(entries) > lines else entries

    def _parse_gemini_entry(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single Gemini message."""
        role = msg.get("role")

        # Model response
        if role == "model":
            content = msg.get("content")
            tool_calls = msg.get("tool_calls", [])

            if tool_calls:
                # Return first tool call
                tc = tool_calls[0]
                return {
                    "type": "tool_call",
                    "name": tc.get("name", ""),
                    "arguments": tc.get("arguments", {}),
                }

            if content:
                return {"type": "message", "text": content}

        # Tool output
        if role == "tool":
            return {
                "type": "tool_output",
                "output": msg.get("content", ""),
            }

        return None

    def tail_formatted(
        self,
        path: Path,
        lines: int = 50,
        include_timestamps: bool = False,
    ) -> str:
        """
        Return formatted, human-readable transcript output.

        Args:
            path: Path to transcript file
            lines: Maximum number of entries
            include_timestamps: Whether to include timestamps

        Returns:
            Formatted string representation
        """
        entries = self.tail(path, lines)
        parts = []

        for entry in entries:
            entry_type = entry.get("type", "")
            timestamp = entry.get("timestamp", "")

            prefix = ""
            if include_timestamps and timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    prefix = f"[{dt.strftime('%H:%M:%S')}] "
                except (ValueError, AttributeError):
                    prefix = f"[{timestamp}] "

            if entry_type == "message":
                text = entry.get("text", "")
                parts.append(f"{prefix}{text}")
            elif entry_type == "reasoning":
                text = entry.get("text", "")
                parts.append(f"{prefix}[thinking] {text}")
            elif entry_type == "tool_call":
                name = entry.get("name", "")
                args = entry.get("arguments", entry.get("input", ""))
                if isinstance(args, dict):
                    args = json.dumps(args, indent=2)
                parts.append(f"{prefix}[tool: {name}] {args}")
            elif entry_type == "tool_output":
                output = entry.get("output", "")
                # Truncate long outputs
                if len(output) > 500:
                    output = output[:500] + "..."
                parts.append(f"{prefix}[output] {output}")

        return "\n\n".join(parts)
