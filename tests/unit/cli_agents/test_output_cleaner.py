"""Tests for CLI output cleaner.

The output cleaner transforms raw CLI output (JSONL, etc.) into clean markdown.
It handles:
1. Parsing JSONL from Codex CLI
2. Extracting ONLY agent_message content (not reasoning or commands)
3. Token counting and large output handling
"""

from mcp_the_force.cli_agents.output_cleaner import (
    OutputCleaner,
    CleanedOutput,
)


class TestCodexOutputCleaning:
    """Tests for cleaning Codex CLI JSONL output."""

    def test_empty_output_returns_empty(self):
        """Empty input returns empty CleanedOutput."""
        cleaner = OutputCleaner()
        result = cleaner.clean("")
        assert result.markdown == ""
        assert result.token_count == 0

    def test_parses_thread_started(self):
        """Extracts thread_id from thread.started event."""
        cleaner = OutputCleaner()
        jsonl = '{"type":"thread.started","thread_id":"abc-123"}'
        result = cleaner.clean(jsonl)
        assert result.thread_id == "abc-123"

    def test_excludes_reasoning_from_output(self):
        """Reasoning traces should NOT appear in output."""
        cleaner = OutputCleaner()
        jsonl = '{"type":"item.completed","item":{"type":"reasoning","text":"Analyzing the problem..."}}'
        result = cleaner.clean(jsonl)
        # Reasoning should NOT be in output
        assert "Analyzing" not in result.markdown
        assert result.markdown == ""

    def test_excludes_command_execution_from_output(self):
        """Command executions should NOT appear in output."""
        cleaner = OutputCleaner()
        jsonl = '{"type":"item.completed","item":{"type":"command_execution","command":"ls -la","aggregated_output":"file1.txt\\nfile2.txt","exit_code":0}}'
        result = cleaner.clean(jsonl)
        # Commands should NOT be in output
        assert "ls -la" not in result.markdown
        assert "file1.txt" not in result.markdown
        assert result.markdown == ""

    def test_extracts_agent_message(self):
        """Extracts agent_message as the only content."""
        cleaner = OutputCleaner()
        jsonl = '{"type":"item.completed","item":{"type":"agent_message","text":"Here is my analysis:\\n\\n1. First point\\n2. Second point"}}'
        result = cleaner.clean(jsonl)
        assert "Here is my analysis" in result.markdown
        assert "First point" in result.markdown

    def test_only_agent_message_extracted(self):
        """Only agent_message content is extracted, not reasoning or commands."""
        cleaner = OutputCleaner()
        jsonl = """{"type":"thread.started","thread_id":"xyz-789"}
{"type":"item.completed","item":{"type":"reasoning","text":"Planning approach"}}
{"type":"item.completed","item":{"type":"command_execution","command":"cat file.py","aggregated_output":"def hello():\\n    pass","exit_code":0}}
{"type":"item.completed","item":{"type":"agent_message","text":"The file contains a hello function."}}"""

        result = cleaner.clean(jsonl)
        assert result.thread_id == "xyz-789"
        # Only agent_message should be in output
        assert result.markdown == "The file contains a hello function."
        # Reasoning and commands should NOT be in output
        assert "Planning approach" not in result.markdown
        assert "cat file.py" not in result.markdown
        assert "def hello()" not in result.markdown

    def test_handles_malformed_json_gracefully(self):
        """Malformed JSON lines are skipped, not errored."""
        cleaner = OutputCleaner()
        jsonl = """{"type":"thread.started","thread_id":"abc"}
not valid json
{"type":"item.completed","item":{"type":"agent_message","text":"Valid content"}}"""

        result = cleaner.clean(jsonl)
        assert result.thread_id == "abc"
        assert "Valid content" in result.markdown

    def test_command_execution_ignored(self):
        """Command executions are ignored (not extracted)."""
        cleaner = OutputCleaner()
        jsonl = '{"type":"item.completed","item":{"type":"command_execution","command":"rm /nonexistent","aggregated_output":"","exit_code":1,"status":"completed"}}'
        result = cleaner.clean(jsonl)
        # Commands should not appear in output
        assert "rm" not in result.markdown
        assert result.markdown == ""


class TestTokenCounting:
    """Tests for token counting in cleaned output."""

    def test_token_count_increases_with_content(self):
        """Token count reflects content size."""
        cleaner = OutputCleaner()

        small = cleaner.clean(
            '{"type":"item.completed","item":{"type":"agent_message","text":"Hi"}}'
        )
        large = cleaner.clean(
            '{"type":"item.completed","item":{"type":"agent_message","text":"'
            + "word " * 1000
            + '"}}'
        )

        assert large.token_count > small.token_count
        assert small.token_count > 0

    def test_exceeds_threshold_flag(self):
        """exceeds_threshold is set when output is large."""
        cleaner = OutputCleaner(token_threshold=100)

        small = cleaner.clean(
            '{"type":"item.completed","item":{"type":"agent_message","text":"Hi"}}'
        )
        large = cleaner.clean(
            '{"type":"item.completed","item":{"type":"agent_message","text":"'
            + "This is a much longer text that should exceed the threshold. " * 50
            + '"}}'
        )

        assert not small.exceeds_threshold
        assert large.exceeds_threshold


class TestNonCodexOutput:
    """Tests for handling non-Codex CLI output (plain text)."""

    def test_plain_text_passthrough(self):
        """Plain text (non-JSON) passes through unchanged."""
        cleaner = OutputCleaner()
        plain = """Here is my analysis:

1. The code looks good
2. Consider adding tests

```python
def example():
    pass
```"""
        result = cleaner.clean(plain)
        assert "Here is my analysis" in result.markdown
        assert "def example():" in result.markdown

    def test_mixed_json_and_text(self):
        """Mixed content (some JSON, some plain) is handled."""
        cleaner = OutputCleaner()
        mixed = """Some preamble text
{"type":"item.completed","item":{"type":"agent_message","text":"JSON content"}}
More plain text at the end"""

        result = cleaner.clean(mixed)
        # Should include both JSON-extracted and plain text content
        assert "JSON content" in result.markdown


class TestCleanedOutputDataclass:
    """Tests for the CleanedOutput dataclass."""

    def test_dataclass_fields(self):
        """CleanedOutput has all expected fields."""
        output = CleanedOutput(
            markdown="# Test",
            token_count=10,
            exceeds_threshold=False,
            thread_id="abc-123",
        )
        assert output.markdown == "# Test"
        assert output.token_count == 10
        assert output.exceeds_threshold is False
        assert output.thread_id == "abc-123"

    def test_thread_id_optional(self):
        """thread_id is optional (defaults to None)."""
        output = CleanedOutput(
            markdown="test",
            token_count=5,
            exceeds_threshold=False,
        )
        assert output.thread_id is None


class TestLargeOutputHandling:
    """Tests for handling large outputs (write to file)."""

    def test_save_to_file_creates_file(self, tmp_path):
        """Large outputs can be saved to a file."""
        from mcp_the_force.cli_agents.output_cleaner import OutputFileHandler

        handler = OutputFileHandler(output_dir=str(tmp_path))
        markdown = "# Large Output\n\n" + ("Content line\n" * 500)

        file_path = handler.save_to_file(markdown, session_id="test-session")

        assert file_path.exists()
        assert file_path.read_text() == markdown
        assert "test-session" in file_path.name

    def test_save_to_file_returns_path(self, tmp_path):
        """save_to_file returns the file path."""
        from mcp_the_force.cli_agents.output_cleaner import OutputFileHandler

        handler = OutputFileHandler(output_dir=str(tmp_path))
        markdown = "# Test"

        file_path = handler.save_to_file(markdown, session_id="my-session")

        assert file_path is not None
        assert file_path.suffix == ".md"

    def test_format_summary_with_file_link(self, tmp_path):
        """Summary includes link to full output file."""
        from mcp_the_force.cli_agents.output_cleaner import OutputFileHandler

        handler = OutputFileHandler(output_dir=str(tmp_path))
        summary = "This is a summary of the work done."
        file_path = tmp_path / "output.md"
        file_path.write_text("full content")

        result = handler.format_summary_with_link(summary, file_path)

        assert summary in result
        assert str(file_path) in result
        assert "full output" in result.lower() or "details" in result.lower()

    def test_default_output_dir_is_tmp(self):
        """Default output directory is /tmp or system temp."""
        from mcp_the_force.cli_agents.output_cleaner import OutputFileHandler
        import tempfile

        handler = OutputFileHandler()

        assert (
            handler.output_dir.startswith(tempfile.gettempdir())
            or handler.output_dir == "/tmp"
        )
