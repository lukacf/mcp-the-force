"""Unit tests for JSON extraction utility."""

import pytest
from mcp_second_brain.utils.json_extractor import extract_json, parse_json_response


class TestJsonExtractor:
    """Test JSON extraction from various response formats."""

    def test_clean_json(self):
        """Test extraction of already clean JSON."""
        content = '{"result": true, "count": 42}'
        assert extract_json(content) == content

    def test_markdown_wrapped_json_object(self):
        """Test extraction from markdown code block with json language."""
        content = """Here is the result:
        
```json
{
  "name": "Alice",
  "age": 30,
  "active": true
}
```

That's the user data."""
        expected = """{
  "name": "Alice",
  "age": 30,
  "active": true
}"""
        assert extract_json(content) == expected

    def test_markdown_wrapped_json_array(self):
        """Test extraction from markdown code block with array."""
        content = """```json
[
  {"id": 1, "name": "Item 1"},
  {"id": 2, "name": "Item 2"}
]
```"""
        expected = """[
  {"id": 1, "name": "Item 1"},
  {"id": 2, "name": "Item 2"}
]"""
        assert extract_json(content) == expected

    def test_markdown_without_language(self):
        """Test extraction from plain markdown code block."""
        content = """The response is:

```
{"status": "success", "code": 200}
```

Please process accordingly."""
        expected = '{"status": "success", "code": 200}'
        assert extract_json(content) == expected

    def test_json_with_prefix(self):
        """Test extraction when JSON has a common prefix."""
        content = 'JSON: {"error": null, "data": {"items": [1, 2, 3]}}'
        expected = '{"error": null, "data": {"items": [1, 2, 3]}}'
        assert extract_json(content) == expected

    def test_json_with_trailing_text(self):
        """Test extraction when JSON has trailing text."""
        content = '{"status": "ok"} and that concludes the response.'
        expected = '{"status": "ok"}'
        assert extract_json(content) == expected

    def test_nested_json(self):
        """Test extraction of JSON with nested objects."""
        content = """Here's the config:
        
```json
{
  "server": {
    "host": "localhost",
    "port": 8080,
    "ssl": {
      "enabled": true,
      "cert": "/path/to/cert"
    }
  },
  "features": ["auth", "logging", "metrics"]
}
```"""
        assert '"server"' in extract_json(content)
        assert '"ssl"' in extract_json(content)
        assert '"features"' in extract_json(content)

    def test_json_with_escaped_quotes(self):
        """Test extraction of JSON with escaped quotes."""
        content = '{"message": "He said \\"Hello\\" to me", "status": "ok"}'
        assert extract_json(content) == content

    def test_invalid_json_raises_error(self):
        """Test that invalid JSON raises ValueError."""
        content = "This is not JSON at all"
        with pytest.raises(ValueError):
            extract_json(content)

    def test_incomplete_json_raises_error(self):
        """Test that incomplete JSON raises ValueError."""
        content = '{"name": "Alice", "age":'  # Missing closing
        with pytest.raises(ValueError):
            extract_json(content)

    def test_parse_json_response(self):
        """Test the parse_json_response helper."""
        content = """```json
{"success": true, "items": [1, 2, 3]}
```"""
        result = parse_json_response(content)
        assert result == {"success": True, "items": [1, 2, 3]}

    def test_multiple_json_blocks(self):
        """Test extraction when multiple JSON blocks exist (takes first)."""
        content = """First block:
```json
{"first": true}
```

Second block:
```json
{"second": true}
```"""
        extract_json(content)
        parsed = parse_json_response(content)
        assert parsed == {"first": True}

    def test_json_in_text_without_blocks(self):
        """Test extraction of bare JSON from text."""
        content = (
            'The server returned {"error": false, "data": [1, 2, 3]} successfully.'
        )
        expected = '{"error": false, "data": [1, 2, 3]}'
        assert extract_json(content) == expected
