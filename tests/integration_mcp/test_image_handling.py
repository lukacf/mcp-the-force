"""Integration tests for image handling in MCP tools."""

import pytest
import uuid


# Use anyio with asyncio backend only
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.parametrize("anyio_backend", ["asyncio"], indirect=True),
]


class TestImageHandlingMCP:
    """Test image handling through MCP protocol."""

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
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool(
                "chat_with_gemini3_pro_preview",
                {
                    "instructions": "Describe this image",
                    "output_format": "text",
                    "context": [],
                    "session_id": f"mcp-gemini-vision-{uuid.uuid4()}",
                    "images": [test_image_path],
                },
            )

            # Should succeed (mock adapter will handle it)
            assert (
                not result.is_error
            ), f"Tool call failed: {getattr(result, 'error_message', 'Unknown')}"

            content = result.content
            assert isinstance(content, list)
            assert len(content) >= 1

    async def test_openai_with_images_parameter(self, mcp_server, test_image_path):
        """Test OpenAI GPT-4.1 tool accepts images parameter via MCP."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool(
                "chat_with_gpt41",
                {
                    "instructions": "Describe this image",
                    "output_format": "text",
                    "context": [],
                    "session_id": f"mcp-openai-vision-{uuid.uuid4()}",
                    "images": [test_image_path],
                },
            )

            # Should succeed (mock adapter will handle it)
            assert (
                not result.is_error
            ), f"Tool call failed: {getattr(result, 'error_message', 'Unknown')}"

            content = result.content
            assert isinstance(content, list)
            assert len(content) >= 1

    async def test_anthropic_with_images_parameter(self, mcp_server, test_image_path):
        """Test Anthropic tool accepts images parameter via MCP."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool(
                "chat_with_claude45_sonnet",
                {
                    "instructions": "Describe this image",
                    "output_format": "text",
                    "session_id": f"mcp-claude-vision-{uuid.uuid4()}",
                    "images": [test_image_path],
                },
            )

            # Should succeed (mock adapter will handle it)
            assert (
                not result.is_error
            ), f"Tool call failed: {getattr(result, 'error_message', 'Unknown')}"

            content = result.content
            assert isinstance(content, list)
            assert len(content) >= 1

    async def test_grok41_with_images_parameter(self, mcp_server, test_image_path):
        """Test Grok 4.1 tool accepts images parameter via MCP."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool(
                "chat_with_grok41",
                {
                    "instructions": "Describe this image",
                    "output_format": "text",
                    "session_id": f"mcp-grok-vision-{uuid.uuid4()}",
                    "images": [test_image_path],
                },
            )

            # Should succeed (mock adapter will handle it)
            assert (
                not result.is_error
            ), f"Tool call failed: {getattr(result, 'error_message', 'Unknown')}"

            content = result.content
            assert isinstance(content, list)
            assert len(content) >= 1

    async def test_non_vision_model_rejects_images(self, mcp_server, test_image_path):
        """Test that non-vision models reject images parameter."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport
        from fastmcp.exceptions import ToolError

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            # Should raise an error because deep research models don't support vision
            # The images parameter is filtered out by capability system
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool(
                    "research_with_o4_mini_deep_research",
                    {
                        "instructions": "Describe this image",
                        "output_format": "text",
                        "session_id": f"mcp-research-vision-{uuid.uuid4()}",
                        "images": [
                            test_image_path
                        ],  # Deep research models don't support vision
                    },
                )

            # The error should mention 'images' as unexpected
            assert "images" in str(exc_info.value).lower()

    async def test_empty_images_parameter_allowed(self, mcp_server):
        """Test that empty images list works for vision-capable models."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            # Call with empty images list on a vision-capable model
            # (Grok doesn't have images param in schema, so use Gemini)
            result = await client.call_tool(
                "chat_with_gemini3_pro_preview",
                {
                    "instructions": "Hello",
                    "output_format": "text",
                    "context": [],
                    "session_id": f"mcp-gemini-empty-{uuid.uuid4()}",
                    "images": [],  # Empty list should be allowed
                },
            )

            # Should succeed - empty images shouldn't cause issues
            assert not result.is_error, f"Empty images should be allowed: {getattr(result, 'error_message', 'Unknown')}"

    async def test_multiple_images(self, mcp_server, tmp_path):
        """Test handling multiple images."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        # Create multiple test images
        png_data = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01"
            b"\x00\x00\x00\x01"
            b"\x08\x02"
            b"\x00\x00\x00"
            b"\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        image_paths = []
        for i in range(3):
            path = tmp_path / f"test_image_{i}.png"
            path.write_bytes(png_data)
            image_paths.append(str(path))

        transport = FastMCPTransport(mcp_server)
        async with Client(transport) as client:
            result = await client.call_tool(
                "chat_with_gemini3_pro_preview",
                {
                    "instructions": "Compare these images",
                    "output_format": "text",
                    "context": [],
                    "session_id": f"mcp-gemini-multi-{uuid.uuid4()}",
                    "images": image_paths,
                },
            )

            assert not result.is_error, f"Multiple images should work: {getattr(result, 'error_message', 'Unknown')}"

    async def test_session_continuation_after_images(self, mcp_server, test_image_path):
        """Test that sessions continue correctly after images are stripped from history."""
        from fastmcp import Client
        from fastmcp.client import FastMCPTransport

        session_id = f"mcp-session-image-test-{uuid.uuid4()}"
        transport = FastMCPTransport(mcp_server)

        async with Client(transport) as client:
            # First call with image
            result1 = await client.call_tool(
                "chat_with_gemini3_pro_preview",
                {
                    "instructions": "Describe this image",
                    "output_format": "text",
                    "context": [],
                    "session_id": session_id,
                    "images": [test_image_path],
                },
            )
            assert (
                not result1.is_error
            ), f"First call failed: {getattr(result1, 'error_message', 'Unknown')}"

            # Second call WITHOUT image (continuation)
            # This should work because images are stripped from history
            result2 = await client.call_tool(
                "chat_with_gemini3_pro_preview",
                {
                    "instructions": "What did you describe in the previous message?",
                    "output_format": "text",
                    "context": [],
                    "session_id": session_id,  # Same session
                    "images": [],  # No images this time
                },
            )
            assert not result2.is_error, f"Session continuation failed: {getattr(result2, 'error_message', 'Unknown')}"
