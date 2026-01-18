"""
Unit Tests: CLI output parsing.

Tests parsing logic in isolation via plugin's parse_output() method.
"""


class TestClaudePluginParsing:
    """Unit tests for Claude plugin parsing."""

    def test_extracts_session_id_from_init_event(self):
        """Parser extracts session_id from the init event."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        output = '[{"type":"system","subtype":"init","session_id":"test-123"}]'

        plugin = ClaudePlugin()
        result = plugin.parse_output(output)

        assert result.session_id == "test-123"

    def test_extracts_content_from_result_event(self):
        """Parser extracts content from the result event."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        output = '[{"type":"result","subtype":"success","result":"Hello world"}]'

        plugin = ClaudePlugin()
        result = plugin.parse_output(output)

        assert result.content == "Hello world"

    def test_handles_multiple_events(self):
        """Parser handles array with multiple events."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        output = """[
            {"type":"system","subtype":"init","session_id":"abc-123"},
            {"type":"assistant","text":"thinking..."},
            {"type":"result","subtype":"success","result":"Done!"}
        ]"""

        plugin = ClaudePlugin()
        result = plugin.parse_output(output)

        assert result.session_id == "abc-123"
        assert "Done" in result.content

    def test_handles_empty_output(self):
        """Parser handles empty/invalid output gracefully."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        result = plugin.parse_output("")

        assert result.session_id is None
        assert result.content == ""

    def test_handles_malformed_json(self):
        """Parser handles malformed JSON without crashing."""
        from mcp_the_force.cli_plugins.claude import ClaudePlugin

        plugin = ClaudePlugin()
        result = plugin.parse_output("not valid json {{{")

        assert result.session_id is None


class TestGeminiPluginParsing:
    """Unit tests for Gemini plugin parsing."""

    def test_extracts_session_id(self):
        """Parser extracts session_id from JSON object."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        output = '{"session_id":"gemini-456","response":"Hello"}'

        plugin = GeminiPlugin()
        result = plugin.parse_output(output)

        assert result.session_id == "gemini-456"

    def test_extracts_response_as_content(self):
        """Parser extracts response field as content."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        output = '{"session_id":"gemini-456","response":"The answer is 42"}'

        plugin = GeminiPlugin()
        result = plugin.parse_output(output)

        assert result.content == "The answer is 42"

    def test_handles_missing_fields(self):
        """Parser handles missing optional fields."""
        from mcp_the_force.cli_plugins.gemini import GeminiPlugin

        output = '{"response":"Just content"}'

        plugin = GeminiPlugin()
        result = plugin.parse_output(output)

        assert result.session_id is None
        assert result.content == "Just content"


class TestCodexPluginParsing:
    """Unit tests for Codex plugin parsing."""

    def test_extracts_thread_id_as_session_id(self):
        """Parser extracts thread_id and maps to session_id."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        output = '{"thread_id":"thread-789","type":"thread.started"}'

        plugin = CodexPlugin()
        result = plugin.parse_output(output)

        assert result.session_id == "thread-789"

    def test_handles_jsonl_multiline(self):
        """Parser handles JSONL (multiple JSON lines)."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        output = """{"thread_id":"thread-789","type":"thread.started"}
{"type":"turn.started"}
{"type":"item.completed","content":"Result here"}
{"type":"turn.completed"}"""

        plugin = CodexPlugin()
        result = plugin.parse_output(output)

        assert result.session_id == "thread-789"
        assert "Result" in result.content

    def test_aggregates_content_from_multiple_items(self):
        """Parser aggregates content from item.completed events."""
        from mcp_the_force.cli_plugins.codex import CodexPlugin

        output = """{"thread_id":"t1","type":"thread.started"}
{"type":"item.completed","content":"Part 1"}
{"type":"item.completed","content":"Part 2"}"""

        plugin = CodexPlugin()
        result = plugin.parse_output(output)

        assert "Part 1" in result.content
        assert "Part 2" in result.content


class TestParsedCLIResponse:
    """Unit tests for ParsedCLIResponse dataclass."""

    def test_dataclass_creation(self):
        """ParsedCLIResponse can be created with required fields."""
        from mcp_the_force.cli_plugins.base import ParsedCLIResponse

        response = ParsedCLIResponse(
            session_id="test-id",
            content="test content",
        )

        assert response.session_id == "test-id"
        assert response.content == "test content"

    def test_optional_metadata(self):
        """ParsedCLIResponse supports optional metadata."""
        from mcp_the_force.cli_plugins.base import ParsedCLIResponse

        response = ParsedCLIResponse(
            session_id="test-id",
            content="content",
            metadata={"key": "value"},
        )

        assert response.metadata["key"] == "value"
