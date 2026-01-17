"""Image formatting utilities for different AI provider APIs."""

import base64
from typing import List

from mcp_the_force.utils.image_loader import LoadedImage


def format_for_openai(images: List[LoadedImage]) -> List[dict]:
    """Format images for OpenAI API.

    OpenAI expects images as data URLs in image_url format:
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}

    Args:
        images: List of LoadedImage objects

    Returns:
        List of OpenAI-formatted image content blocks
    """
    return [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{img.mime_type};base64,{base64.b64encode(img.data).decode()}"
            },
        }
        for img in images
    ]


def format_for_anthropic(images: List[LoadedImage]) -> List[dict]:
    """Format images for Anthropic Claude API.

    Anthropic expects images as base64 source:
    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}}

    Args:
        images: List of LoadedImage objects

    Returns:
        List of Anthropic-formatted image content blocks
    """
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img.mime_type,
                "data": base64.b64encode(img.data).decode(),
            },
        }
        for img in images
    ]
