"""Integration tests for image handling in MCP tools.

NOTE: These tests are skipped because the vision-capable chat_with_* tools
are now internal-only (accessed via consult_with, which doesn't support images).
The underlying image handling functionality still exists in the internal tools.
"""

import pytest


# Use anyio with asyncio backend only
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.parametrize("anyio_backend", ["asyncio"], indirect=True),
    pytest.mark.skip(
        reason="chat_with_* tools are internal-only; consult_with doesn't support images yet"
    ),
]


class TestImageHandlingMCP:
    """Test image handling through MCP protocol.

    Skipped: Vision-capable models (chat_with_gemini3_pro_preview, etc.)
    are now internal-only tools routed via consult_with, which doesn't
    expose the images parameter.
    """

    @pytest.fixture
    def test_image_path(self, tmp_path):
        """Create a test PNG image file."""
        image_path = tmp_path / "test_image.png"
        # Minimal valid PNG header + data
        png_data = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\rIHDR"  # IHDR chunk
            b"\x00\x00\x00\x01"  # width: 1
            b"\x00\x00\x00\x01"  # height: 1
            b"\x08\x02"  # bit depth: 8, color type: RGB
            b"\x00\x00\x00"  # compression, filter, interlace
            b"\x90wS\xde"  # CRC
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"  # IDAT
            b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND
        )
        image_path.write_bytes(png_data)
        return str(image_path)

    async def test_gemini_with_images_parameter(self, mcp_server, test_image_path):
        """Test Gemini tool accepts images parameter via MCP."""
        pytest.skip("chat_with_* tools are internal-only")

    async def test_openai_with_images_parameter(self, mcp_server, test_image_path):
        """Test OpenAI GPT-4.1 tool accepts images parameter via MCP."""
        pytest.skip("chat_with_* tools are internal-only")

    async def test_anthropic_with_images_parameter(self, mcp_server, test_image_path):
        """Test Anthropic tool accepts images parameter via MCP."""
        pytest.skip("chat_with_* tools are internal-only")

    async def test_grok41_with_images_parameter(self, mcp_server, test_image_path):
        """Test Grok 4.1 tool accepts images parameter via MCP."""
        pytest.skip("chat_with_* tools are internal-only")

    async def test_non_vision_model_rejects_images(self, mcp_server, test_image_path):
        """Test that non-vision models reject images parameter."""
        pytest.skip("chat_with_* tools are internal-only")

    async def test_empty_images_parameter_allowed(self, mcp_server):
        """Test that empty images list works for vision-capable models."""
        pytest.skip("chat_with_* tools are internal-only")

    async def test_multiple_images(self, mcp_server, tmp_path):
        """Test handling multiple images."""
        pytest.skip("chat_with_* tools are internal-only")

    async def test_session_continuation_after_images(self, mcp_server, test_image_path):
        """Test that sessions continue correctly after images are stripped from history."""
        pytest.skip("chat_with_* tools are internal-only")
