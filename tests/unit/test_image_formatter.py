"""Tests for image formatting utility - TDD."""

import base64

from mcp_the_force.utils.image_loader import LoadedImage


class TestOpenAIFormatter:
    """Test OpenAI image formatting."""

    def test_format_single_image_for_openai(self):
        """Should format a single image for OpenAI API."""
        from mcp_the_force.utils.image_formatter import format_for_openai

        image = LoadedImage(
            data=b"fake png data",
            mime_type="image/png",
            source="file",
            original_path="/path/to/image.png",
        )

        result = format_for_openai([image])

        assert len(result) == 1
        assert result[0]["type"] == "image_url"
        assert "image_url" in result[0]

        # Check base64 data URL format
        url = result[0]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")
        encoded_data = url.split(",")[1]
        assert base64.b64decode(encoded_data) == b"fake png data"

    def test_format_multiple_images_for_openai(self):
        """Should format multiple images for OpenAI API."""
        from mcp_the_force.utils.image_formatter import format_for_openai

        images = [
            LoadedImage(b"png data", "image/png", "file", "/a.png"),
            LoadedImage(b"jpeg data", "image/jpeg", "url", "https://x.com/b.jpg"),
        ]

        result = format_for_openai(images)

        assert len(result) == 2
        assert all(r["type"] == "image_url" for r in result)
        assert "image/png" in result[0]["image_url"]["url"]
        assert "image/jpeg" in result[1]["image_url"]["url"]

    def test_empty_list_for_openai(self):
        """Should return empty list for empty input."""
        from mcp_the_force.utils.image_formatter import format_for_openai

        result = format_for_openai([])
        assert result == []


class TestAnthropicFormatter:
    """Test Anthropic/Claude image formatting."""

    def test_format_single_image_for_anthropic(self):
        """Should format a single image for Anthropic API."""
        from mcp_the_force.utils.image_formatter import format_for_anthropic

        image = LoadedImage(
            data=b"fake jpeg data",
            mime_type="image/jpeg",
            source="file",
            original_path="/path/to/image.jpg",
        )

        result = format_for_anthropic([image])

        assert len(result) == 1
        assert result[0]["type"] == "image"
        assert "source" in result[0]
        assert result[0]["source"]["type"] == "base64"
        assert result[0]["source"]["media_type"] == "image/jpeg"

        # Check base64 encoding
        encoded = result[0]["source"]["data"]
        assert base64.b64decode(encoded) == b"fake jpeg data"

    def test_format_multiple_images_for_anthropic(self):
        """Should format multiple images for Anthropic API."""
        from mcp_the_force.utils.image_formatter import format_for_anthropic

        images = [
            LoadedImage(b"gif data", "image/gif", "file", "/a.gif"),
            LoadedImage(b"png data", "image/png", "url", "https://x.com/b.png"),
        ]

        result = format_for_anthropic(images)

        assert len(result) == 2
        assert all(r["type"] == "image" for r in result)
        assert all(r["source"]["type"] == "base64" for r in result)
        assert result[0]["source"]["media_type"] == "image/gif"
        assert result[1]["source"]["media_type"] == "image/png"

    def test_empty_list_for_anthropic(self):
        """Should return empty list for empty input."""
        from mcp_the_force.utils.image_formatter import format_for_anthropic

        result = format_for_anthropic([])
        assert result == []
