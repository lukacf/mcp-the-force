"""
RCT: CLI Output Format Tests

These tests validate that our parsers can handle real CLI output formats.
Uses sample output data to ensure parser compatibility.

Gate 0 requirement: All tests must be green before Phase 1.

NOTE: Sample outputs will be collected by running the spike scripts.
This file defines the MINIMUM VIABLE SCHEMA for each CLI.
"""

import pytest
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ParsedCLIOutput:
    """Minimum viable parsed output from any CLI.

    This defines what we MUST extract from CLI output.
    All other fields are optional metadata.
    """

    content: str  # The actual response text
    session_id: Optional[str]  # CLI's session/thread ID for resume
    success: bool  # Whether the CLI execution succeeded
    raw_output: str  # Original unparsed output for debugging

    # Optional metadata
    model: Optional[str] = None
    execution_time_ms: Optional[int] = None
    token_count: Optional[int] = None


class BaseCLIParser:
    """Base class for CLI output parsers.

    Each CLI parser must implement parse() to extract ParsedCLIOutput.
    """

    def parse(self, raw_output: str) -> ParsedCLIOutput:  # noqa: ARG002
        raise NotImplementedError("Subclasses must implement parse()")


class ClaudeOutputParser(BaseCLIParser):
    """Parser for Claude Code CLI JSON output.

    Claude Code outputs JSON with --output-format json.
    Expected structure (based on docs and testing):
    {
        "session_id": "...",
        "result": "..." or "message": "...",
        ...
    }
    """

    def parse(self, raw_output: str) -> ParsedCLIOutput:
        try:
            data = json.loads(raw_output)

            # Extract content - try multiple possible field names
            content = (
                data.get("result")
                or data.get("message")
                or data.get("content")
                or data.get("response")
                or ""
            )

            # Handle nested content structure
            if isinstance(content, list):
                # Content might be [{"type": "text", "text": "..."}]
                content = " ".join(
                    item.get("text", str(item))
                    for item in content
                    if isinstance(item, dict)
                )

            # Extract session_id - try multiple possible field names
            session_id = (
                data.get("session_id")
                or data.get("sessionId")
                or data.get("conversation_id")
            )

            return ParsedCLIOutput(
                content=str(content),
                session_id=session_id,
                success=True,
                raw_output=raw_output,
                model=data.get("model"),
            )
        except json.JSONDecodeError:
            return ParsedCLIOutput(
                content="",
                session_id=None,
                success=False,
                raw_output=raw_output,
            )


class GeminiOutputParser(BaseCLIParser):
    """Parser for Gemini CLI JSON output.

    Gemini CLI outputs JSON with --output-format json.
    May output JSONL (one JSON object per line).
    """

    def parse(self, raw_output: str) -> ParsedCLIOutput:
        try:
            # Try parsing as single JSON first
            try:
                data = json.loads(raw_output)
                return self._parse_json_object(data, raw_output)
            except json.JSONDecodeError:
                pass

            # Try JSONL (one JSON per line)
            lines = raw_output.strip().split("\n")
            events = []
            for line in lines:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            if events:
                return self._parse_jsonl_events(events, raw_output)

            # Fallback: treat as plain text
            return ParsedCLIOutput(
                content=raw_output,
                session_id=None,
                success=True,
                raw_output=raw_output,
            )

        except Exception:
            return ParsedCLIOutput(
                content="",
                session_id=None,
                success=False,
                raw_output=raw_output,
            )

    def _parse_json_object(
        self, data: Dict[str, Any], raw_output: str
    ) -> ParsedCLIOutput:
        """Parse a single JSON object."""
        content = (
            data.get("text")
            or data.get("content")
            or data.get("message")
            or data.get("response")
            or ""
        )

        session_id = data.get("session_id") or data.get("sessionId") or data.get("id")

        return ParsedCLIOutput(
            content=str(content),
            session_id=session_id,
            success=True,
            raw_output=raw_output,
            model=data.get("model"),
        )

    def _parse_jsonl_events(self, events: list, raw_output: str) -> ParsedCLIOutput:
        """Parse JSONL events and extract final content."""
        # Look for the final message or response event
        content_parts = []
        session_id = None
        model = None

        for event in events:
            # Try to extract text from various event types
            if "text" in event:
                content_parts.append(event["text"])
            elif "content" in event:
                content_parts.append(str(event["content"]))
            elif "message" in event:
                content_parts.append(str(event["message"]))

            # Look for session/model info
            if not session_id:
                session_id = (
                    event.get("session_id") or event.get("sessionId") or event.get("id")
                )
            if not model:
                model = event.get("model")

        return ParsedCLIOutput(
            content="".join(content_parts),
            session_id=session_id,
            success=True,
            raw_output=raw_output,
            model=model,
        )


class CodexOutputParser(BaseCLIParser):
    """Parser for Codex CLI JSONL output.

    Codex CLI outputs JSONL with --json flag.
    Each line is a separate event.
    Expected event types: message, tool_call, etc.
    """

    def parse(self, raw_output: str) -> ParsedCLIOutput:
        try:
            lines = raw_output.strip().split("\n")
            events = []

            for line in lines:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            if not events:
                return ParsedCLIOutput(
                    content="",
                    session_id=None,
                    success=False,
                    raw_output=raw_output,
                )

            return self._parse_events(events, raw_output)

        except Exception:
            return ParsedCLIOutput(
                content="",
                session_id=None,
                success=False,
                raw_output=raw_output,
            )

    def _parse_events(self, events: list, raw_output: str) -> ParsedCLIOutput:
        """Parse Codex JSONL events."""
        content_parts = []
        thread_id = None
        model = None

        for event in events:
            event_type = event.get("type") or event.get("event")

            # Extract thread_id (Codex's session identifier)
            if not thread_id:
                thread_id = (
                    event.get("thread_id")
                    or event.get("threadId")
                    or event.get("session_id")
                )

            # Extract content from message events
            if event_type == "message" or "content" in event or "text" in event:
                text = event.get("text") or event.get("content") or event.get("message")
                if text:
                    content_parts.append(str(text))

            # Look for model info
            if not model:
                model = event.get("model")

        return ParsedCLIOutput(
            content="".join(content_parts),
            session_id=thread_id,  # Codex uses thread_id as session identifier
            success=True,
            raw_output=raw_output,
            model=model,
        )


# =============================================================================
# RCT Tests - These define the MINIMUM VIABLE SCHEMA
# =============================================================================


class TestClaudeOutputParser:
    """RCT: Claude Code CLI output parsing."""

    @pytest.fixture
    def parser(self):
        return ClaudeOutputParser()

    def test_parse_minimal_json(self, parser):
        """Parser handles minimal JSON with just content."""
        raw = json.dumps({"result": "Hello, world!"})
        parsed = parser.parse(raw)

        assert parsed.success is True
        assert parsed.content == "Hello, world!"

    def test_parse_with_session_id(self, parser):
        """Parser extracts session_id correctly."""
        raw = json.dumps(
            {
                "session_id": "claude-abc-123",
                "result": "Response text",
            }
        )
        parsed = parser.parse(raw)

        assert parsed.session_id == "claude-abc-123"
        assert parsed.content == "Response text"

    def test_parse_alternative_session_id_field(self, parser):
        """Parser handles sessionId (camelCase) field."""
        raw = json.dumps(
            {
                "sessionId": "claude-def-456",
                "message": "Response text",
            }
        )
        parsed = parser.parse(raw)

        assert parsed.session_id == "claude-def-456"
        assert parsed.content == "Response text"

    def test_parse_nested_content(self, parser):
        """Parser handles nested content array structure."""
        raw = json.dumps(
            {
                "session_id": "test-session",
                "content": [
                    {"type": "text", "text": "First part. "},
                    {"type": "text", "text": "Second part."},
                ],
            }
        )
        parsed = parser.parse(raw)

        assert "First part" in parsed.content
        assert "Second part" in parsed.content

    def test_parse_invalid_json(self, parser):
        """Parser handles invalid JSON gracefully."""
        raw = "This is not JSON"
        parsed = parser.parse(raw)

        assert parsed.success is False
        assert parsed.content == ""
        assert parsed.raw_output == raw

    def test_preserves_raw_output(self, parser):
        """Parser always preserves raw output for debugging."""
        raw = json.dumps({"result": "test", "extra_field": "value"})
        parsed = parser.parse(raw)

        assert parsed.raw_output == raw
        assert "extra_field" in parsed.raw_output


class TestGeminiOutputParser:
    """RCT: Gemini CLI output parsing."""

    @pytest.fixture
    def parser(self):
        return GeminiOutputParser()

    def test_parse_single_json(self, parser):
        """Parser handles single JSON object."""
        raw = json.dumps({"text": "Gemini response"})
        parsed = parser.parse(raw)

        assert parsed.success is True
        assert parsed.content == "Gemini response"

    def test_parse_jsonl(self, parser):
        """Parser handles JSONL (one JSON per line)."""
        events = [
            {"type": "start", "model": "gemini-3-pro"},
            {"type": "content", "text": "Part 1 "},
            {"type": "content", "text": "Part 2"},
            {"type": "end"},
        ]
        raw = "\n".join(json.dumps(e) for e in events)
        parsed = parser.parse(raw)

        assert parsed.success is True
        assert "Part 1" in parsed.content
        assert "Part 2" in parsed.content

    def test_parse_with_session_id(self, parser):
        """Parser extracts session_id from JSONL events."""
        events = [
            {"session_id": "gemini-session-xyz", "type": "start"},
            {"text": "Response"},
        ]
        raw = "\n".join(json.dumps(e) for e in events)
        parsed = parser.parse(raw)

        assert parsed.session_id == "gemini-session-xyz"

    def test_parse_empty_output(self, parser):
        """Parser handles empty output."""
        parsed = parser.parse("")

        assert parsed.success is True  # Empty is valid, just no content
        assert parsed.content == ""

    def test_preserves_raw_output(self, parser):
        """Parser always preserves raw output."""
        raw = '{"text": "test"}'
        parsed = parser.parse(raw)

        assert parsed.raw_output == raw


class TestCodexOutputParser:
    """RCT: Codex CLI output parsing."""

    @pytest.fixture
    def parser(self):
        return CodexOutputParser()

    def test_parse_jsonl_events(self, parser):
        """Parser handles Codex JSONL events."""
        events = [
            {"type": "message", "text": "Codex response"},
            {"type": "done", "thread_id": "codex-thread-123"},
        ]
        raw = "\n".join(json.dumps(e) for e in events)
        parsed = parser.parse(raw)

        assert parsed.success is True
        assert "Codex response" in parsed.content

    def test_extract_thread_id(self, parser):
        """Parser extracts thread_id for session resume."""
        events = [
            {"thread_id": "thread-abc-123", "type": "start"},
            {"type": "message", "content": "Response"},
        ]
        raw = "\n".join(json.dumps(e) for e in events)
        parsed = parser.parse(raw)

        assert parsed.session_id == "thread-abc-123"

    def test_alternative_thread_id_field(self, parser):
        """Parser handles threadId (camelCase) field."""
        events = [
            {"threadId": "thread-def-456", "type": "init"},
            {"text": "Response"},
        ]
        raw = "\n".join(json.dumps(e) for e in events)
        parsed = parser.parse(raw)

        assert parsed.session_id == "thread-def-456"

    def test_parse_empty_jsonl(self, parser):
        """Parser handles empty/invalid JSONL."""
        parsed = parser.parse("")

        assert parsed.success is False

    def test_parse_mixed_valid_invalid_lines(self, parser):
        """Parser skips invalid lines and parses valid ones."""
        raw = """{"text": "Valid line 1"}
Not valid JSON
{"text": "Valid line 2"}"""
        parsed = parser.parse(raw)

        assert parsed.success is True
        assert "Valid line 1" in parsed.content
        assert "Valid line 2" in parsed.content

    def test_preserves_raw_output(self, parser):
        """Parser always preserves raw output."""
        events = [{"type": "message", "text": "test"}]
        raw = "\n".join(json.dumps(e) for e in events)
        parsed = parser.parse(raw)

        assert parsed.raw_output == raw


# =============================================================================
# Integration-style tests with sample data
# =============================================================================


class TestRealWorldSamples:
    """Tests using sample outputs collected from spike scripts.

    NOTE: These samples will be populated after running the spike scripts.
    For now, they use synthetic samples based on documentation.
    """

    # Sample Claude output (based on docs)
    CLAUDE_SAMPLE = json.dumps(
        {
            "session_id": "550e8400-e29b-41d4-a716-446655440000",
            "result": "I'll help you with that task.",
            "model": "claude-sonnet-4-5",
            "cost_usd": 0.003,
        }
    )

    # Sample Gemini output (based on docs)
    GEMINI_SAMPLE = "\n".join(
        [
            json.dumps({"type": "modelInfo", "model": "gemini-3-pro-preview"}),
            json.dumps({"type": "text", "text": "Here's my analysis:"}),
            json.dumps({"type": "text", "text": " The code looks good."}),
            json.dumps({"type": "turnComplete", "session_id": "gemini-xyz"}),
        ]
    )

    # Sample Codex output (based on docs)
    CODEX_SAMPLE = "\n".join(
        [
            json.dumps({"type": "init", "thread_id": "th_abc123", "model": "gpt-4o"}),
            json.dumps({"type": "message", "content": "I've reviewed the code."}),
            json.dumps({"type": "done", "success": True}),
        ]
    )

    def test_parse_claude_sample(self):
        parser = ClaudeOutputParser()
        parsed = parser.parse(self.CLAUDE_SAMPLE)

        assert parsed.success is True
        assert "help you" in parsed.content
        assert parsed.session_id is not None

    def test_parse_gemini_sample(self):
        parser = GeminiOutputParser()
        parsed = parser.parse(self.GEMINI_SAMPLE)

        assert parsed.success is True
        assert "analysis" in parsed.content.lower()

    def test_parse_codex_sample(self):
        parser = CodexOutputParser()
        parsed = parser.parse(self.CODEX_SAMPLE)

        assert parsed.success is True
        assert "reviewed" in parsed.content.lower()
        assert parsed.session_id == "th_abc123"
