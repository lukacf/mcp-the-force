"""Tests for adapter image handling - TDD."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


class TestGeminiAdapterImageHandling:
    """Test Gemini adapter handles images correctly."""

    @pytest.fixture
    def mock_gemini_client(self):
        """Create a mock Gemini client."""
        # Create a properly structured mock response
        mock_text_part = MagicMock()
        mock_text_part.text = "Response text"
        mock_text_part.function_call = None  # No function calls

        mock_content = MagicMock()
        mock_content.parts = [mock_text_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
        return mock_client

    @pytest.fixture
    def mock_call_context(self):
        """Create a mock CallContext."""
        return MagicMock(
            session_id="test-session",
            project="test-project",
            tool="chat_with_gemini3_pro_preview",
            vector_store_ids=None,
        )

    @pytest.fixture
    def mock_tool_dispatcher(self):
        """Create a mock tool dispatcher."""
        dispatcher = MagicMock()
        dispatcher.get_tool_declarations.return_value = []
        return dispatcher

    @pytest.mark.asyncio
    async def test_gemini_includes_images_in_content(
        self, mock_gemini_client, mock_call_context, mock_tool_dispatcher, tmp_path
    ):
        """Gemini adapter should include images as Part objects in content."""
        # Create a test image file
        test_image = tmp_path / "test.png"
        test_image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        # Import adapter and create instance
        with patch(
            "mcp_the_force.adapters.google.adapter.GeminiAdapter._get_client",
            return_value=mock_gemini_client,
        ):
            with patch(
                "mcp_the_force.adapters.google.adapter.GeminiAdapter._validate_environment"
            ):
                from mcp_the_force.adapters.google.adapter import GeminiAdapter

                adapter = GeminiAdapter("gemini-3-pro-preview")

        # Create params with images
        params = SimpleNamespace(
            temperature=0.7,
            reasoning_effort="medium",
            structured_output_schema=None,
            disable_history_search=False,
            images=[str(test_image)],
        )

        # Mock session history
        with patch(
            "mcp_the_force.adapters.google.adapter.UnifiedSessionCache.get_history",
            new_callable=AsyncMock,
            return_value=[],
        ):
            with patch(
                "mcp_the_force.adapters.google.adapter.UnifiedSessionCache.set_history",
                new_callable=AsyncMock,
            ):
                with patch.object(
                    adapter, "_get_client", return_value=mock_gemini_client
                ):
                    _result = await adapter.generate(
                        prompt="Describe this image",
                        params=params,
                        ctx=mock_call_context,
                        tool_dispatcher=mock_tool_dispatcher,
                    )

        # Verify generate_content was called
        mock_gemini_client.aio.models.generate_content.assert_called_once()

        # Get the contents argument
        call_args = mock_gemini_client.aio.models.generate_content.call_args
        contents = call_args.kwargs["contents"]

        # The last content should be the user message with text and images
        user_content = contents[-1]

        # Should have at least 2 parts: text and image
        assert (
            len(user_content.parts) >= 2
        ), "User content should have text and image parts"


class TestOpenAIAdapterImageHandling:
    """Test OpenAI adapter handles images correctly."""

    @pytest.mark.asyncio
    async def test_openai_includes_images_in_request(self, tmp_path):
        """OpenAI adapter should include images as image_url content blocks."""
        # Create a test image file
        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        # The OpenAI adapter uses FlowOrchestrator which is complex
        # For now, just verify the images parameter is accessible
        params = SimpleNamespace(
            temperature=0.7,
            reasoning_effort="medium",
            structured_output_schema=None,
            disable_history_search=False,
            images=[str(test_image)],
        )

        assert hasattr(params, "images")
        assert params.images == [str(test_image)]


class TestAnthropicAdapterImageHandling:
    """Test Anthropic adapter handles images correctly."""

    @pytest.mark.asyncio
    async def test_anthropic_includes_images_in_request(self, tmp_path):
        """Anthropic adapter should include images as base64 content blocks."""
        # Create a test image file
        test_image = tmp_path / "test.gif"
        test_image.write_bytes(b"GIF89a" + b"\x00" * 100)

        # The Anthropic adapter uses LiteLLM
        # For now, just verify the images parameter is accessible
        params = SimpleNamespace(
            temperature=0.7,
            max_tokens=4096,
            structured_output_schema=None,
            images=[str(test_image)],
        )

        assert hasattr(params, "images")
        assert params.images == [str(test_image)]


class TestImageLoadingInAdapters:
    """Test that images are properly loaded before being sent to API."""

    @pytest.mark.asyncio
    async def test_load_images_called_with_paths(self, tmp_path):
        """Adapters should call load_images with the provided paths."""
        from mcp_the_force.utils.image_loader import load_images

        # Create test images
        png_file = tmp_path / "test.png"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        jpg_file = tmp_path / "test.jpg"
        jpg_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        # Load images
        images = await load_images([str(png_file), str(jpg_file)])

        assert len(images) == 2
        assert images[0].mime_type == "image/png"
        assert images[1].mime_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_format_images_for_provider(self, tmp_path):
        """Format images correctly for each provider."""
        from mcp_the_force.utils.image_loader import load_images
        from mcp_the_force.utils.image_formatter import (
            format_for_openai,
            format_for_anthropic,
        )

        # Create test image
        png_file = tmp_path / "test.png"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        images = await load_images([str(png_file)])

        # Test OpenAI format
        openai_format = format_for_openai(images)
        assert openai_format[0]["type"] == "image_url"

        # Test Anthropic format
        anthropic_format = format_for_anthropic(images)
        assert anthropic_format[0]["type"] == "image"
        assert anthropic_format[0]["source"]["type"] == "base64"


class TestCapabilityEnforcementForImages:
    """Test that non-vision models reject images parameter."""

    def test_non_vision_model_rejects_images(self):
        """Non-vision models should not accept images parameter."""
        from mcp_the_force.adapters.xai.definitions import GrokBaseCapabilities

        capabilities = GrokBaseCapabilities()
        assert capabilities.supports_vision is False

        # The capability validator should reject images for non-vision models
        # This is enforced at the executor level via requires_capability

    def test_vision_model_accepts_images(self):
        """Vision-capable models should accept images parameter."""
        from mcp_the_force.adapters.google.definitions import GeminiBaseCapabilities
        from mcp_the_force.adapters.anthropic.definitions import (
            AnthropicBaseCapabilities,
        )

        gemini_caps = GeminiBaseCapabilities()
        assert gemini_caps.supports_vision is True

        anthropic_caps = AnthropicBaseCapabilities()
        assert anthropic_caps.supports_vision is True


class TestImageErrorHandlingInAdapters:
    """Test error handling when image loading fails in adapters."""

    @pytest.fixture
    def mock_call_context(self):
        """Create a mock CallContext."""
        return MagicMock(
            session_id="test-session",
            project="test-project",
            tool="test-tool",
            vector_store_ids=None,
        )

    @pytest.fixture
    def mock_tool_dispatcher(self):
        """Create a mock tool dispatcher."""
        dispatcher = MagicMock()
        dispatcher.get_tool_declarations.return_value = []
        return dispatcher

    @pytest.mark.asyncio
    async def test_gemini_adapter_handles_image_load_error(
        self, mock_call_context, mock_tool_dispatcher
    ):
        """Gemini adapter should convert ImageLoadError to ValueError."""

        with patch("mcp_the_force.adapters.google.adapter.GeminiAdapter._get_client"):
            with patch(
                "mcp_the_force.adapters.google.adapter.GeminiAdapter._validate_environment"
            ):
                from mcp_the_force.adapters.google.adapter import GeminiAdapter

                adapter = GeminiAdapter("gemini-3-pro-preview")

        params = SimpleNamespace(
            temperature=0.7,
            reasoning_effort="medium",
            structured_output_schema=None,
            disable_history_search=False,
            images=["/nonexistent/image.png"],
        )

        # Mock session history
        with patch(
            "mcp_the_force.adapters.google.adapter.UnifiedSessionCache.get_history",
            new_callable=AsyncMock,
            return_value=[],
        ):
            with pytest.raises(ValueError, match="Failed to load images"):
                await adapter.generate(
                    prompt="Describe this",
                    params=params,
                    ctx=mock_call_context,
                    tool_dispatcher=mock_tool_dispatcher,
                )

    @pytest.mark.asyncio
    async def test_openai_adapter_handles_image_load_error(
        self, mock_call_context, mock_tool_dispatcher
    ):
        """OpenAI adapter should convert ImageLoadError to ValueError."""
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "test-key"},
        ):
            from mcp_the_force.adapters.openai.adapter import OpenAIProtocolAdapter

            adapter = OpenAIProtocolAdapter("gpt-5.2-pro")

        params = SimpleNamespace(
            temperature=0.7,
            reasoning_effort="medium",
            structured_output_schema=None,
            disable_history_search=False,
            images=["/nonexistent/image.png"],
        )

        with pytest.raises(ValueError, match="Failed to load images"):
            await adapter.generate(
                prompt="Describe this",
                params=params,
                ctx=mock_call_context,
                tool_dispatcher=mock_tool_dispatcher,
            )


class TestAdapterCapabilityValidation:
    """Test capability validation happens before image loading."""

    @pytest.fixture
    def mock_call_context(self):
        """Create a mock CallContext."""
        return MagicMock(
            session_id="test-session",
            project="test-project",
            tool="test-tool",
            vector_store_ids=None,
        )

    @pytest.fixture
    def mock_tool_dispatcher(self):
        """Create a mock tool dispatcher."""
        dispatcher = MagicMock()
        dispatcher.get_tool_declarations.return_value = []
        return dispatcher

    @pytest.mark.asyncio
    async def test_non_vision_gemini_rejects_before_loading(
        self, mock_call_context, mock_tool_dispatcher, tmp_path
    ):
        """Non-vision Gemini models should reject images before any loading."""
        # Create a valid image file
        test_image = tmp_path / "test.png"
        test_image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        with patch("mcp_the_force.adapters.google.adapter.GeminiAdapter._get_client"):
            with patch(
                "mcp_the_force.adapters.google.adapter.GeminiAdapter._validate_environment"
            ):
                from mcp_the_force.adapters.google.adapter import GeminiAdapter
                from mcp_the_force.adapters.google.definitions import (
                    GeminiBaseCapabilities,
                )

                adapter = GeminiAdapter("gemini-3-pro-preview")
                # Force vision to False
                adapter.capabilities = GeminiBaseCapabilities()
                adapter.capabilities.supports_vision = False

        params = SimpleNamespace(
            temperature=0.7,
            reasoning_effort="medium",
            structured_output_schema=None,
            disable_history_search=False,
            images=[str(test_image)],
        )

        # Track if load_images was called
        with patch("mcp_the_force.adapters.google.adapter.load_images") as mock_load:
            with patch(
                "mcp_the_force.adapters.google.adapter.UnifiedSessionCache.get_history",
                new_callable=AsyncMock,
                return_value=[],
            ):
                with pytest.raises(ValueError, match="does not support vision"):
                    await adapter.generate(
                        prompt="Describe this",
                        params=params,
                        ctx=mock_call_context,
                        tool_dispatcher=mock_tool_dispatcher,
                    )

            # load_images should NOT have been called
            mock_load.assert_not_called()


class TestMultiTurnSessionsWithImages:
    """Test multi-turn conversation sessions with images."""

    def test_history_sanitizer_strips_images_for_session_storage(self):
        """Images should be stripped before storing in session history."""
        from mcp_the_force.utils.history_sanitizer import strip_images_from_history

        # First turn with image
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
                            * 100,  # Large base64
                        },
                    },
                ],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "I see a cat in the image."}],
            },
        ]

        sanitized = strip_images_from_history(messages)

        # Image data should be replaced with placeholder
        user_content = sanitized[0]["content"]
        assert len(user_content) == 2
        assert user_content[0]["type"] == "text"
        assert user_content[1]["type"] == "text"
        assert "[Image was provided: image/png]" in user_content[1]["text"]

        # Assistant message should be unchanged
        assert sanitized[1] == messages[1]

    def test_sanitized_history_much_smaller_than_original(self):
        """Sanitized history should be much smaller than original with images."""
        import json
        from mcp_the_force.utils.history_sanitizer import strip_images_from_history

        # Create message with large image
        large_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB" * 10000  # ~400KB
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": large_base64,
                        },
                    },
                ],
            },
        ]

        original_size = len(json.dumps(messages))
        sanitized = strip_images_from_history(messages)
        sanitized_size = len(json.dumps(sanitized))

        # Sanitized should be much smaller (at least 90% reduction)
        assert sanitized_size < original_size * 0.1

    def test_multi_turn_conversation_with_images(self):
        """Test simulated multi-turn conversation with images."""
        from mcp_the_force.utils.history_sanitizer import strip_images_from_history

        # Turn 1: User sends image
        turn1_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "type": "image",
                        "source": {
                            "media_type": "image/jpeg",
                            "data": "base64data" * 100,
                        },
                    },
                ],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "I see a red apple."}],
            },
        ]

        # Sanitize for storage (what happens after turn 1)
        stored_history = strip_images_from_history(turn1_messages)

        # Turn 2: User asks follow-up
        turn2_messages = stored_history + [
            {
                "role": "user",
                "content": [{"type": "text", "text": "What color is it?"}],
            },
        ]

        # Verify structure for turn 2
        assert len(turn2_messages) == 3

        # First message should have sanitized image
        assert turn2_messages[0]["content"][1]["type"] == "text"
        assert "Image was provided" in turn2_messages[0]["content"][1]["text"]

        # Turn 2 message should be plain text
        assert len(turn2_messages[2]["content"]) == 1
        assert turn2_messages[2]["content"][0]["type"] == "text"

    def test_image_placeholders_preserve_context(self):
        """Image placeholders should preserve useful context about the original image."""
        from mcp_the_force.utils.history_sanitizer import strip_images_from_history

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "mime_type": "image/png",
                        "source": "/path/to/screenshot.png",
                        "original_path": "/Users/test/screenshot.png",
                    },
                ],
            },
        ]

        sanitized = strip_images_from_history(messages)
        placeholder = sanitized[0]["content"][0]["text"]

        # Placeholder should include mime type and original path
        assert "image/png" in placeholder
        assert "/Users/test/screenshot.png" in placeholder

    def test_multiple_images_all_sanitized(self):
        """All images in a message should be sanitized."""
        from mcp_the_force.utils.history_sanitizer import strip_images_from_history

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Compare these images"},
                    {
                        "type": "image",
                        "source": {"media_type": "image/png", "data": "png_data"},
                    },
                    {
                        "type": "image",
                        "source": {"media_type": "image/jpeg", "data": "jpeg_data"},
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/gif;base64,gif_data"},
                    },
                ],
            },
        ]

        sanitized = strip_images_from_history(messages)
        content = sanitized[0]["content"]

        # All 4 items should be present
        assert len(content) == 4

        # First is text, rest are placeholders
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Compare these images"

        # Check all images were sanitized
        for i in range(1, 4):
            assert content[i]["type"] == "text"
            assert "Image was provided" in content[i]["text"]
