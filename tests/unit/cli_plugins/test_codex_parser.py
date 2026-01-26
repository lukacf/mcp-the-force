"""Tests for Codex CLI parser.

Verifies that:
1. Parser extracts ONLY agent_message content (not reasoning or commands)
2. Parser extracts content only from the LAST turn (not all turns)
3. On resume, previous turn content is ignored
4. Thread ID is extracted correctly
"""

from mcp_the_force.cli_plugins.codex.parser import CodexParser


class TestCodexParserAgentMessageOnly:
    """Test that CodexParser extracts only agent_message content."""

    def test_excludes_reasoning_from_output(self):
        """Reasoning traces should NOT appear in output - only agent messages."""
        parser = CodexParser()

        jsonl = """
{"type":"thread.started","thread_id":"thread_123"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"reasoning","text":"**Preparing simple greeting**"}}
{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"Hello."}}
{"type":"turn.completed"}
"""
        result = parser.parse(jsonl)

        assert result.session_id == "thread_123"
        assert result.content == "Hello."
        assert "reasoning" not in result.content.lower()
        assert "Preparing" not in result.content

    def test_excludes_command_execution_from_output(self):
        """Command executions should NOT appear in output - only agent messages."""
        parser = CodexParser()

        jsonl = """
{"type":"thread.started","thread_id":"thread_456"}
{"type":"turn.started"}
{"type":"item.completed","item":{"type":"command_execution","command":"ls -la","aggregated_output":"file1.txt\\nfile2.txt","exit_code":0}}
{"type":"item.completed","item":{"type":"agent_message","text":"I found 2 files in the directory."}}
{"type":"turn.completed"}
"""
        result = parser.parse(jsonl)

        assert result.content == "I found 2 files in the directory."
        assert "ls -la" not in result.content
        assert "file1.txt" not in result.content

    def test_concatenates_multiple_agent_messages(self):
        """Multiple agent messages in one turn should be joined."""
        parser = CodexParser()

        jsonl = """
{"type":"thread.started","thread_id":"thread_789"}
{"type":"turn.started"}
{"type":"item.completed","item":{"type":"agent_message","text":"First part."}}
{"type":"item.completed","item":{"type":"agent_message","text":"Second part."}}
{"type":"turn.completed"}
"""
        result = parser.parse(jsonl)

        assert "First part." in result.content
        assert "Second part." in result.content


class TestCodexParserLastTurnOnly:
    """Test that parser extracts only the last turn's content."""

    def test_single_turn_extracts_all_content(self):
        """Single turn should extract all content."""
        parser = CodexParser()

        jsonl = """{"thread_id": "thread_abc", "type": "thread.started"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "Hello, I can help you."}}
{"type": "turn.completed"}"""

        result = parser.parse(jsonl)

        assert result.session_id == "thread_abc"
        assert "Hello, I can help you." in result.content

    def test_multiple_turns_extracts_only_last_turn(self):
        """Multiple turns should only extract the LAST turn's agent_message content.

        This is critical for resume sessions - we don't want to save
        the entire session transcript, only the new response.
        """
        parser = CodexParser()

        # Simulates output from a resumed session with 3 turns
        jsonl = """{"thread_id": "thread_abc", "type": "thread.started"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "Turn 1: First response"}}
{"type": "turn.completed"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "Turn 2: Second response"}}
{"type": "turn.completed"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "command_execution", "command": "/bin/zsh -lc 'echo done'", "aggregated_output": "done", "exit_code": 0}}
{"type": "item.completed", "item": {"type": "agent_message", "text": "Turn 3: This is the latest response"}}
{"type": "turn.completed"}"""

        result = parser.parse(jsonl)

        # Should ONLY contain the last turn's agent_message
        assert result.content == "Turn 3: This is the latest response"

        # Should NOT contain command execution output
        assert "echo done" not in result.content

        # Should NOT contain previous turns' content
        assert "Turn 1" not in result.content
        assert "Turn 2" not in result.content

    def test_thread_id_preserved_with_multiple_turns(self):
        """Thread ID should still be extracted even when parsing only last turn."""
        parser = CodexParser()

        jsonl = """{"thread_id": "thread_xyz", "type": "thread.started"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "Old content"}}
{"type": "turn.completed"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "New content"}}
{"type": "turn.completed"}"""

        result = parser.parse(jsonl)

        assert result.session_id == "thread_xyz"
        assert "New content" in result.content
        assert "Old content" not in result.content

    def test_incomplete_last_turn_still_extracted(self):
        """If last turn is incomplete (no turn.completed), still extract it."""
        parser = CodexParser()

        jsonl = """{"thread_id": "thread_abc", "type": "thread.started"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "First complete turn"}}
{"type": "turn.completed"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "Partial turn content"}}"""

        result = parser.parse(jsonl)

        # Should extract the partial last turn, not the complete previous turn
        assert "Partial turn content" in result.content
        assert "First complete turn" not in result.content

    def test_no_turn_markers_extracts_all_content(self):
        """If no turn markers present, extract all content (backward compat)."""
        parser = CodexParser()

        jsonl = """{"thread_id": "thread_abc", "type": "thread.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "Response without turn markers"}}"""

        result = parser.parse(jsonl)

        assert "Response without turn markers" in result.content

    def test_only_agent_message_from_last_turn(self):
        """Only agent_message items from last turn should be extracted."""
        parser = CodexParser()

        jsonl = """{"thread_id": "thread_abc", "type": "thread.started"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "reasoning", "text": "Old reasoning"}}
{"type": "item.completed", "item": {"type": "agent_message", "text": "Old message"}}
{"type": "turn.completed"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "reasoning", "text": "New reasoning"}}
{"type": "item.completed", "item": {"type": "command_execution", "command": "ls new", "aggregated_output": "new files", "exit_code": 0}}
{"type": "item.completed", "item": {"type": "agent_message", "text": "New message"}}
{"type": "turn.completed"}"""

        result = parser.parse(jsonl)

        # Only agent_message from last turn
        assert result.content == "New message"

        # No reasoning or commands
        assert "reasoning" not in result.content.lower()
        assert "ls new" not in result.content

        # No old content
        assert "Old" not in result.content
