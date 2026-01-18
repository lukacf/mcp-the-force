"""
Unit Tests: CLI output parsers.

Tests parser logic in isolation - no subprocess, no I/O.
"""


class TestClaudeParser:
    """Unit tests for ClaudeParser."""

    def test_extracts_session_id_from_init_event(self):
        """Parser extracts session_id from the init event."""
        from mcp_the_force.cli_agents.parsers.claude import ClaudeParser

        output = '[{"type":"system","subtype":"init","session_id":"test-123"}]'

        parser = ClaudeParser()
        result = parser.parse(output)

        assert result.session_id == "test-123"

    def test_extracts_content_from_result_event(self):
        """Parser extracts content from the result event."""
        from mcp_the_force.cli_agents.parsers.claude import ClaudeParser

        output = '[{"type":"result","subtype":"success","result":"Hello world"}]'

        parser = ClaudeParser()
        result = parser.parse(output)

        assert result.content == "Hello world"

    def test_handles_multiple_events(self):
        """Parser handles array with multiple events."""
        from mcp_the_force.cli_agents.parsers.claude import ClaudeParser

        output = """[
            {"type":"system","subtype":"init","session_id":"abc-123"},
            {"type":"assistant","text":"thinking..."},
            {"type":"result","subtype":"success","result":"Done!"}
        ]"""

        parser = ClaudeParser()
        result = parser.parse(output)

        assert result.session_id == "abc-123"
        assert "Done" in result.content

    def test_handles_empty_output(self):
        """Parser handles empty/invalid output gracefully."""
        from mcp_the_force.cli_agents.parsers.claude import ClaudeParser

        parser = ClaudeParser()
        result = parser.parse("")

        assert result.session_id is None
        assert result.content == ""

    def test_handles_malformed_json(self):
        """Parser handles malformed JSON without crashing."""
        from mcp_the_force.cli_agents.parsers.claude import ClaudeParser

        parser = ClaudeParser()
        result = parser.parse("not valid json {{{")

        assert result.session_id is None


class TestGeminiParser:
    """Unit tests for GeminiParser."""

    def test_extracts_session_id(self):
        """Parser extracts session_id from JSON object."""
        from mcp_the_force.cli_agents.parsers.gemini import GeminiParser

        output = '{"session_id":"gemini-456","response":"Hello"}'

        parser = GeminiParser()
        result = parser.parse(output)

        assert result.session_id == "gemini-456"

    def test_extracts_response_as_content(self):
        """Parser extracts response field as content."""
        from mcp_the_force.cli_agents.parsers.gemini import GeminiParser

        output = '{"session_id":"gemini-456","response":"The answer is 42"}'

        parser = GeminiParser()
        result = parser.parse(output)

        assert result.content == "The answer is 42"

    def test_handles_missing_fields(self):
        """Parser handles missing optional fields."""
        from mcp_the_force.cli_agents.parsers.gemini import GeminiParser

        output = '{"response":"Just content"}'

        parser = GeminiParser()
        result = parser.parse(output)

        assert result.session_id is None
        assert result.content == "Just content"


class TestCodexParser:
    """Unit tests for CodexParser."""

    def test_extracts_thread_id_as_session_id(self):
        """Parser extracts thread_id and maps to session_id."""
        from mcp_the_force.cli_agents.parsers.codex import CodexParser

        output = '{"thread_id":"thread-789","type":"thread.started"}'

        parser = CodexParser()
        result = parser.parse(output)

        assert result.session_id == "thread-789"

    def test_handles_jsonl_multiline(self):
        """Parser handles JSONL (multiple JSON lines)."""
        from mcp_the_force.cli_agents.parsers.codex import CodexParser

        output = """{"thread_id":"thread-789","type":"thread.started"}
{"type":"turn.started"}
{"type":"item.completed","content":"Result here"}
{"type":"turn.completed"}"""

        parser = CodexParser()
        result = parser.parse(output)

        assert result.session_id == "thread-789"
        assert "Result" in result.content

    def test_aggregates_content_from_multiple_items(self):
        """Parser aggregates content from item.completed events."""
        from mcp_the_force.cli_agents.parsers.codex import CodexParser

        output = """{"thread_id":"t1","type":"thread.started"}
{"type":"item.completed","content":"Part 1"}
{"type":"item.completed","content":"Part 2"}"""

        parser = CodexParser()
        result = parser.parse(output)

        assert "Part 1" in result.content
        assert "Part 2" in result.content


class TestParsedCLIResponse:
    """Unit tests for ParsedCLIResponse dataclass."""

    def test_dataclass_creation(self):
        """ParsedCLIResponse can be created with required fields."""
        from mcp_the_force.cli_agents.parsers.base import ParsedCLIResponse

        response = ParsedCLIResponse(
            session_id="test-id",
            content="test content",
        )

        assert response.session_id == "test-id"
        assert response.content == "test content"

    def test_optional_metadata(self):
        """ParsedCLIResponse supports optional metadata."""
        from mcp_the_force.cli_agents.parsers.base import ParsedCLIResponse

        response = ParsedCLIResponse(
            session_id="test-id",
            content="content",
            metadata={"key": "value"},
        )

        assert response.metadata["key"] == "value"
