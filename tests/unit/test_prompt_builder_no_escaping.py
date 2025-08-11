"""Test that PromptBuilder preserves code content without XML escaping."""

from mcp_the_force.optimization.prompt_builder import PromptBuilder


class TestPromptBuilderNoEscaping:
    """Test that file content is preserved without XML escaping."""

    def test_preserves_python_code_syntax(self):
        """Test that Python code with <, >, ->, & is preserved exactly."""
        builder = PromptBuilder()

        # Python code with characters that would be XML-escaped
        python_content = """def test(x: int) -> str:
    if x < 5 and y > 3:
        return "x & y"
    # Generic type: List[Dict[str, Any]]
    data: Dict[str, Any] = {"key": "value"}
    return f"<result>{data}</result>"
"""

        inline_files = [("test.py", python_content, 100)]

        prompt = builder.build_prompt(
            instructions="Analyze this code",
            output_format="List issues",
            inline_files=inline_files,
            all_files=["test.py"],
            overflow_files=[],
        )

        # Check that the content is preserved exactly
        assert "def test(x: int) -> str:" in prompt
        assert "if x < 5 and y > 3:" in prompt
        assert 'return "x & y"' in prompt
        assert "List[Dict[str, Any]]" in prompt
        assert 'return f"<result>{data}</result>"' in prompt

        # Ensure NO HTML entities appear
        assert "&gt;" not in prompt
        assert "&lt;" not in prompt
        assert "&amp;" not in prompt
        assert "&quot;" not in prompt

    def test_preserves_xml_like_content(self):
        """Test that XML-like content in files is preserved."""
        builder = PromptBuilder()

        # Content that looks like XML but should be preserved
        xml_like_content = """# This file contains XML examples
config = '''<config>
    <setting name="debug" value="true"/>
    <users>
        <user id="1" name="Alice & Bob"/>
    </users>
</config>'''

# Parse with: tree = ET.fromstring(config)
"""

        inline_files = [("config.py", xml_like_content, 50)]

        prompt = builder.build_prompt(
            instructions="Review config",
            output_format="Summary",
            inline_files=inline_files,
            all_files=["config.py"],
            overflow_files=[],
        )

        # Check exact content preservation
        assert '<setting name="debug" value="true"/>' in prompt
        assert '<user id="1" name="Alice & Bob"/>' in prompt
        assert "tree = ET.fromstring(config)" in prompt

    def test_preserves_special_characters_in_multiple_files(self):
        """Test multiple files with special characters."""
        builder = PromptBuilder()

        file1 = """def compare(a: int, b: int) -> bool:
    return a < b or a > 100
"""

        file2 = """# HTML template
template = "<div class='container'>{content}</div>"
"""

        file3 = """// JavaScript
if (x && y || z > 5) {
    console.log("a < b");
}
"""

        inline_files = [
            ("compare.py", file1, 50),
            ("template.py", file2, 30),
            ("script.js", file3, 40),
        ]

        prompt = builder.build_prompt(
            instructions="Analyze all files",
            output_format="Report",
            inline_files=inline_files,
            all_files=["compare.py", "template.py", "script.js"],
            overflow_files=[],
        )

        # Check all content is preserved
        assert "return a < b or a > 100" in prompt
        assert "<div class='container'>{content}</div>" in prompt
        assert 'console.log("a < b")' in prompt
        assert "if (x && y || z > 5)" in prompt

    def test_control_characters_are_sanitized(self):
        """Test that control characters are removed but normal content preserved."""
        builder = PromptBuilder()

        # Content with control characters
        content_with_control = "Normal text\x00\x01\x02\nLine 2\tTabbed\rReturn"

        inline_files = [("test.txt", content_with_control, 20)]

        prompt = builder.build_prompt(
            instructions="Test",
            output_format="Test",
            inline_files=inline_files,
            all_files=["test.txt"],
            overflow_files=[],
        )

        # Control chars (< 32 except \t\n\r) should be removed
        assert "\x00" not in prompt
        assert "\x01" not in prompt
        assert "\x02" not in prompt

        # But tabs, newlines, returns should be preserved
        assert "Normal text\nLine 2\tTabbed\rReturn" in prompt

    def test_pseudo_xml_structure_preserved(self):
        """Test that the pseudo-XML structure is maintained."""
        builder = PromptBuilder()

        inline_files = [("simple.py", "x = 1", 10)]

        prompt = builder.build_prompt(
            instructions="Test task",
            output_format="JSON",
            inline_files=inline_files,
            all_files=["simple.py"],
            overflow_files=[],
        )

        # Check basic structure
        assert prompt.startswith("<Task>")
        assert prompt.endswith("</Task>")
        assert "<Instructions>Test task</Instructions>" in prompt
        assert "<OutputFormat>JSON</OutputFormat>" in prompt
        assert "<CONTEXT>" in prompt
        assert "</CONTEXT>" in prompt
        assert '<file path="simple.py">x = 1</file>' in prompt
