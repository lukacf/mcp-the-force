"""Tests for history sanitizer utility."""

from mcp_the_force.utils.history_sanitizer import strip_images_from_history


class TestStripImagesFromHistory:
    """Test image stripping from conversation history."""

    def test_empty_messages_returns_empty(self):
        """Empty input should return empty output."""
        result = strip_images_from_history([])
        assert result == []

    def test_text_only_messages_unchanged(self):
        """Messages without images should be unchanged."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there!"}],
            },
        ]
        result = strip_images_from_history(messages)
        assert result == messages

    def test_does_not_mutate_original(self):
        """Original messages should not be modified."""
        original = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "Look at this"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                        },
                    },
                ],
            }
        ]
        # Keep a reference to the original content
        original_content = original[0]["content"][1]

        result = strip_images_from_history(original)

        # Original should be unchanged
        assert original[0]["content"][1] == original_content
        assert original[0]["content"][1]["type"] == "image"
        # Result should be different
        assert result[0]["content"][1]["type"] == "text"

    def test_strips_anthropic_image_format(self):
        """Should strip Anthropic format images (base64 source)."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                        },
                    },
                ],
            }
        ]

        result = strip_images_from_history(messages)

        assert len(result) == 1
        content = result[0]["content"]
        assert len(content) == 2
        assert content[0] == {"type": "text", "text": "Describe this image"}
        assert content[1] == {"type": "text", "text": "[Image was provided: image/png]"}

    def test_strips_gemini_image_format(self):
        """Should strip Gemini format images (source as string path)."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image",
                        "mime_type": "image/jpeg",
                        "source": "/path/to/image.jpg",
                        "original_path": "/path/to/image.jpg",
                    },
                ],
            }
        ]

        result = strip_images_from_history(messages)

        assert len(result) == 1
        content = result[0]["content"]
        assert len(content) == 2
        assert content[0] == {"type": "text", "text": "Describe this image"}
        # Original path is preserved in placeholder for better context
        assert content[1] == {
            "type": "text",
            "text": "[Image was provided: image/jpeg, source: /path/to/image.jpg]",
        }

    def test_strips_openai_data_url_format(self):
        """Should strip OpenAI format images with data URLs."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this photo?"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgc..."
                        },
                    },
                ],
            }
        ]

        result = strip_images_from_history(messages)

        assert len(result) == 1
        content = result[0]["content"]
        assert len(content) == 2
        assert content[0] == {"type": "text", "text": "What's in this photo?"}
        assert content[1] == {
            "type": "text",
            "text": "[Image was provided: image/jpeg]",
        }

    def test_preserves_openai_url_references(self):
        """Should preserve OpenAI format images with regular URLs (not data URLs)."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this webpage screenshot"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/screenshot.png"},
                    },
                ],
            }
        ]

        result = strip_images_from_history(messages)

        # URL references should be preserved (they're not large)
        assert len(result) == 1
        content = result[0]["content"]
        assert len(content) == 2
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == "https://example.com/screenshot.png"

    def test_handles_multiple_images(self):
        """Should strip multiple images in a single message."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "Compare these images"},
                    {
                        "type": "image",
                        "source": {"media_type": "image/png", "data": "base64data1"},
                    },
                    {
                        "type": "image",
                        "source": {"media_type": "image/jpeg", "data": "base64data2"},
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/gif;base64,gifdata"},
                    },
                ],
            }
        ]

        result = strip_images_from_history(messages)

        content = result[0]["content"]
        assert len(content) == 4
        assert content[0] == {"type": "text", "text": "Compare these images"}
        assert content[1] == {"type": "text", "text": "[Image was provided: image/png]"}
        assert content[2] == {
            "type": "text",
            "text": "[Image was provided: image/jpeg]",
        }
        assert content[3] == {"type": "text", "text": "[Image was provided: image/gif]"}

    def test_handles_mixed_conversation(self):
        """Should handle a multi-turn conversation with images in some turns."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "Look at this"},
                    {
                        "type": "image",
                        "source": {"media_type": "image/png", "data": "data1"},
                    },
                ],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "I see a cat"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "What color is it?"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "The cat is orange"}],
            },
        ]

        result = strip_images_from_history(messages)

        # First message should have image stripped
        assert result[0]["content"][1] == {
            "type": "text",
            "text": "[Image was provided: image/png]",
        }
        # Other messages should be unchanged
        assert result[1] == messages[1]
        assert result[2] == messages[2]
        assert result[3] == messages[3]

    def test_handles_string_content(self):
        """Should handle messages with string content (not list)."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        result = strip_images_from_history(messages)

        # String content should be unchanged
        assert result == messages

    def test_handles_non_dict_content_items(self):
        """Should handle content lists with non-dict items."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": ["text string", {"type": "text", "text": "dict item"}],
            }
        ]

        result = strip_images_from_history(messages)

        # Non-dict items should be preserved
        assert result[0]["content"][0] == "text string"
        assert result[0]["content"][1] == {"type": "text", "text": "dict item"}

    def test_handles_missing_media_type(self):
        """Should handle image source without media_type."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"data": "base64data"},  # No media_type
                    },
                ],
            }
        ]

        result = strip_images_from_history(messages)

        assert result[0]["content"][0] == {
            "type": "text",
            "text": "[Image was provided: image/unknown]",
        }

    def test_handles_data_url_without_semicolon(self):
        """Should handle malformed data URLs."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:base64data"},  # Malformed
                    },
                ],
            }
        ]

        result = strip_images_from_history(messages)

        # Should still strip it with unknown mime type
        assert result[0]["content"][0] == {
            "type": "text",
            "text": "[Image was provided: image/unknown]",
        }

    def test_strips_gemini_inline_data_format(self):
        """Should strip Gemini inline_data format (native SDK)."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "inline_data": {
                            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                            "mime_type": "image/png",
                        }
                    },
                ],
            }
        ]

        result = strip_images_from_history(messages)

        assert len(result) == 1
        content = result[0]["content"]
        assert len(content) == 2
        assert content[0] == {"type": "text", "text": "What's in this image?"}
        assert content[1] == {"type": "text", "text": "[Image was provided: image/png]"}

    def test_strips_images_in_nested_tool_results(self):
        """Should strip images nested in tool result fields."""
        messages = [
            {
                "type": "message",
                "role": "tool",
                "content": [{"type": "text", "text": "Tool executed"}],
                "output": {
                    "images": [
                        {
                            "type": "image",
                            "source": {
                                "media_type": "image/jpeg",
                                "data": "base64data",
                            },
                        }
                    ],
                    "text": "Some result",
                },
            }
        ]

        result = strip_images_from_history(messages)

        # Nested image in output should be sanitized
        output = result[0]["output"]
        assert output["images"][0] == {
            "type": "text",
            "text": "[Image was provided: image/jpeg]",
        }
        # Non-image fields preserved
        assert output["text"] == "Some result"

    def test_handles_raw_base64_data(self):
        """Should strip items with raw base64 data (long data strings)."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                        * 50,  # Long base64
                        "mime_type": "image/png",
                    },
                ],
            }
        ]

        result = strip_images_from_history(messages)

        assert result[0]["content"][0] == {
            "type": "text",
            "text": "[Image was provided: image/png]",
        }

    def test_preserves_non_image_content_untouched(self):
        """Should preserve non-image content exactly as-is."""
        original_messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello world"},
                    {
                        "type": "tool_result",
                        "tool_call_id": "123",
                        "content": "Success",
                    },
                ],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I understand"},
                    {"type": "tool_call", "tool": "my_tool", "args": {"x": 1}},
                ],
            },
        ]

        result = strip_images_from_history(original_messages)

        # Should be identical since no images
        assert result == original_messages

    def test_handles_deeply_nested_images(self):
        """Should handle images nested multiple levels deep."""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "Check result"}],
                "data": {
                    "nested": {
                        "result": {
                            "images": [
                                {
                                    "type": "image",
                                    "source": {
                                        "media_type": "image/gif",
                                        "data": "base64",
                                    },
                                }
                            ]
                        }
                    }
                },
            }
        ]

        result = strip_images_from_history(messages)

        # Deeply nested image should be sanitized
        nested_images = result[0]["data"]["nested"]["result"]["images"]
        assert nested_images[0] == {
            "type": "text",
            "text": "[Image was provided: image/gif]",
        }

    def test_strips_url_safe_base64(self):
        """Should strip URL-safe base64 data (uses - and _ instead of + and /)."""
        # URL-safe base64 uses - and _ instead of + and /
        url_safe_base64 = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" * 20
        )
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "data": url_safe_base64,
                        "mime_type": "image/webp",
                    },
                ],
            }
        ]

        result = strip_images_from_history(messages)

        assert result[0]["content"][0] == {
            "type": "text",
            "text": "[Image was provided: image/webp]",
        }

    def test_result_modification_does_not_affect_original(self):
        """Modifying the result should never affect the original messages."""
        original = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            }
        ]

        result = strip_images_from_history(original)

        # Modify the result
        result[0]["content"][0]["text"] = "Modified!"
        result[0]["role"] = "assistant"
        result.append({"new": "message"})

        # Original should be completely unchanged
        assert original[0]["content"][0]["text"] == "Hello"
        assert original[0]["role"] == "user"
        assert len(original) == 1

    def test_deep_copy_prevents_nested_mutation(self):
        """Nested structures in result should be independent from original."""
        original = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "text", "text": "Look at this"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "base64data",
                        },
                    },
                ],
                "metadata": {"nested": {"value": 1}},
            }
        ]

        result = strip_images_from_history(original)

        # Modify deeply nested structure in result
        result[0]["metadata"]["nested"]["value"] = 999

        # Original nested structure should be unchanged
        assert original[0]["metadata"]["nested"]["value"] == 1
