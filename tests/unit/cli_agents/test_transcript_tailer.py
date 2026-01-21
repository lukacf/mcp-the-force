"""
Unit Tests: TranscriptTailer for reading CLI session transcripts.

Tests the TranscriptTailer utility that reads and parses transcripts
from different CLI formats (Codex JSONL, Claude JSONL, Gemini JSON).
"""

import json


class TestTranscriptTailerCodex:
    """Tests for tailing Codex JSONL transcripts."""

    def test_tail_codex_extracts_agent_messages(self, tmp_path):
        """Tailer extracts agent message text from Codex JSONL."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "codex-session.jsonl"
        transcript.write_text(
            '{"type": "thread.started", "thread_id": "t1"}\n'
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "Hello, I will help you."}}\n'
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "Task completed."}}\n'
        )

        tailer = TranscriptTailer(format="codex")
        lines = tailer.tail(transcript, lines=10)

        assert len(lines) == 2
        assert "Hello, I will help you." in lines[0]["text"]
        assert "Task completed." in lines[1]["text"]

    def test_tail_codex_extracts_tool_calls(self, tmp_path):
        """Tailer extracts tool/function calls from Codex JSONL."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "codex-session.jsonl"
        transcript.write_text(
            '{"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": "{\\"cmd\\": \\"ls -la\\"}"}}\n'
            '{"type": "response_item", "payload": {"type": "function_call_output", "output": "file1.txt\\nfile2.txt"}}\n'
        )

        tailer = TranscriptTailer(format="codex")
        lines = tailer.tail(transcript, lines=10)

        assert len(lines) == 2
        assert lines[0]["type"] == "tool_call"
        assert lines[0]["name"] == "exec_command"
        assert lines[1]["type"] == "tool_output"

    def test_tail_codex_extracts_reasoning(self, tmp_path):
        """Tailer extracts reasoning/thinking from Codex JSONL."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "codex-session.jsonl"
        transcript.write_text(
            '{"type": "event_msg", "payload": {"type": "agent_reasoning", "text": "Let me analyze the code structure..."}}\n'
        )

        tailer = TranscriptTailer(format="codex")
        lines = tailer.tail(transcript, lines=10)

        assert len(lines) == 1
        assert lines[0]["type"] == "reasoning"
        assert "analyze the code" in lines[0]["text"]

    def test_tail_codex_with_line_limit(self, tmp_path):
        """Tailer respects line limit parameter."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "codex-session.jsonl"
        lines_data = [
            f'{{"type": "item.completed", "item": {{"type": "agent_message", "text": "Message {i}"}}}}\n'
            for i in range(20)
        ]
        transcript.write_text("".join(lines_data))

        tailer = TranscriptTailer(format="codex")
        lines = tailer.tail(transcript, lines=5)

        # Should return last 5 messages
        assert len(lines) == 5
        assert "Message 15" in lines[0]["text"]
        assert "Message 19" in lines[4]["text"]


class TestTranscriptTailerClaude:
    """Tests for tailing Claude Code JSONL transcripts."""

    def test_tail_claude_extracts_assistant_messages(self, tmp_path):
        """Tailer extracts assistant messages from Claude JSONL."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "claude-session.jsonl"
        transcript.write_text(
            '{"type": "user", "message": {"content": "Help me debug"}}\n'
            '{"type": "assistant", "message": {"content": "I will help you debug the issue."}}\n'
            '{"type": "assistant", "message": {"content": "The bug is in line 42."}}\n'
        )

        tailer = TranscriptTailer(format="claude")
        lines = tailer.tail(transcript, lines=10)

        # Should only extract assistant messages
        assert len(lines) == 2
        assert "help you debug" in lines[0]["text"]
        assert "line 42" in lines[1]["text"]

    def test_tail_claude_extracts_tool_use(self, tmp_path):
        """Tailer extracts tool use from Claude JSONL."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "claude-session.jsonl"
        transcript.write_text(
            '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "/test.py"}}]}}\n'
            '{"type": "tool_result", "content": "def hello(): pass"}\n'
        )

        tailer = TranscriptTailer(format="claude")
        lines = tailer.tail(transcript, lines=10)

        assert len(lines) >= 1
        assert any(entry["type"] == "tool_call" for entry in lines)


class TestTranscriptTailerGemini:
    """Tests for tailing Gemini JSON transcripts."""

    def test_tail_gemini_extracts_model_responses(self, tmp_path):
        """Tailer extracts model responses from Gemini JSON."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "gemini-chat.json"
        transcript.write_text(
            json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "What is Python?"},
                        {
                            "role": "model",
                            "content": "Python is a programming language.",
                        },
                        {"role": "user", "content": "Thanks"},
                        {"role": "model", "content": "You're welcome!"},
                    ]
                }
            )
        )

        tailer = TranscriptTailer(format="gemini")
        lines = tailer.tail(transcript, lines=10)

        # Should only extract model responses
        assert len(lines) == 2
        assert "programming language" in lines[0]["text"]
        assert "welcome" in lines[1]["text"]

    def test_tail_gemini_handles_tool_calls(self, tmp_path):
        """Tailer extracts tool calls from Gemini JSON."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "gemini-chat.json"
        transcript.write_text(
            json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "List files"},
                        {
                            "role": "model",
                            "content": None,
                            "tool_calls": [
                                {"name": "shell", "arguments": {"command": "ls"}}
                            ],
                        },
                        {"role": "tool", "content": "file1.txt\nfile2.txt"},
                    ]
                }
            )
        )

        tailer = TranscriptTailer(format="gemini")
        lines = tailer.tail(transcript, lines=10)

        assert any(entry["type"] == "tool_call" for entry in lines)
        assert any(entry["type"] == "tool_output" for entry in lines)


class TestTranscriptTailerAutoDetect:
    """Tests for auto-detecting transcript format."""

    def test_auto_detect_codex_format(self, tmp_path):
        """Tailer auto-detects Codex JSONL format."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "session.jsonl"
        transcript.write_text('{"type": "thread.started", "thread_id": "t1"}\n')

        tailer = TranscriptTailer.from_file(transcript)
        assert tailer.format == "codex"

    def test_auto_detect_claude_format(self, tmp_path):
        """Tailer auto-detects Claude JSONL format."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            '{"type": "user", "message": {"content": "hello"}}\n'
            '{"type": "assistant", "message": {"content": "hi"}}\n'
        )

        tailer = TranscriptTailer.from_file(transcript)
        assert tailer.format == "claude"

    def test_auto_detect_gemini_format(self, tmp_path):
        """Tailer auto-detects Gemini JSON format."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "chat.json"
        transcript.write_text(json.dumps({"messages": []}))

        tailer = TranscriptTailer.from_file(transcript)
        assert tailer.format == "gemini"


class TestTranscriptTailerFormatting:
    """Tests for formatted output from tailer."""

    def test_format_as_text(self, tmp_path):
        """Tailer formats output as human-readable text."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "Hello"}}\n'
            '{"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": "{\\"cmd\\": \\"ls\\"}"}}\n'
        )

        tailer = TranscriptTailer(format="codex")
        text = tailer.tail_formatted(transcript, lines=10)

        assert "Hello" in text
        assert "exec_command" in text
        assert isinstance(text, str)

    def test_format_includes_timestamps_when_available(self, tmp_path):
        """Tailer includes timestamps in formatted output when available."""
        from mcp_the_force.cli_agents.transcript_tailer import TranscriptTailer

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            '{"timestamp": "2026-01-21T10:00:00Z", "type": "item.completed", "item": {"type": "agent_message", "text": "Hello"}}\n'
        )

        tailer = TranscriptTailer(format="codex")
        text = tailer.tail_formatted(transcript, lines=10, include_timestamps=True)

        assert "10:00" in text or "2026-01-21" in text
