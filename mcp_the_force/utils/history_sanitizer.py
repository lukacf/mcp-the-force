"""Utilities for sanitizing conversation history before storage.

The main purpose is to strip large binary data (like base64-encoded images)
from history to prevent context explosion on subsequent turns.
"""

import copy
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _sanitize_content_item(item: Any) -> Any:
    """Sanitize a single content item, replacing image data with placeholders.

    Args:
        item: A content item (could be dict, string, or other type)

    Returns:
        Sanitized item with image data replaced by placeholders
    """
    if not isinstance(item, dict):
        return item

    item_type = item.get("type", "")

    # Handle Anthropic/custom image format: {"type": "image", "source": {...}}
    if item_type == "image":
        source = item.get("source", {})
        # Anthropic format: source is a dict with media_type
        if isinstance(source, dict):
            media_type = source.get("media_type", "image/unknown")
        else:
            # Custom format: mime_type is a separate field
            media_type = item.get("mime_type", "image/unknown")
        original_path = item.get("original_path", "")
        text = f"[Image was provided: {media_type}]"
        if original_path:
            text = f"[Image was provided: {media_type}, source: {original_path}]"
        return {"type": "text", "text": text}

    # Handle OpenAI format: {"type": "image_url", "image_url": {"url": "data:..."}}
    if item_type == "image_url":
        image_url = item.get("image_url", {})
        url = image_url.get("url", "")
        if url.startswith("data:"):
            # Extract mime type from data URL
            mime_type = (
                url.split(";")[0].replace("data:", "")
                if ";" in url
                else "image/unknown"
            )
            return {"type": "text", "text": f"[Image was provided: {mime_type}]"}
        else:
            # Keep URL references (they're not large)
            return item

    # Handle Gemini inline_data format: {"inline_data": {"data": "...", "mime_type": "..."}}
    if "inline_data" in item:
        inline_data = item.get("inline_data", {})
        if isinstance(inline_data, dict):
            mime_type = inline_data.get("mime_type", "image/unknown")
            return {"type": "text", "text": f"[Image was provided: {mime_type}]"}

    # Handle raw base64 data in various formats
    if "data" in item and isinstance(item.get("data"), str):
        data = item["data"]
        # Check if it looks like base64 image data (typically very long)
        # Support both standard base64 (+/) and URL-safe base64 (-_)
        stripped = (
            data.replace("+", "")
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace("=", "")
        )
        if len(data) > 1000 and stripped.isalnum():
            mime_type = item.get("mime_type", item.get("media_type", "image/unknown"))
            return {"type": "text", "text": f"[Image was provided: {mime_type}]"}

    return item


def _sanitize_content_list(content: List[Any]) -> List[Any]:
    """Sanitize a list of content items.

    Args:
        content: List of content items

    Returns:
        New list with sanitized items
    """
    new_content = []
    images_replaced = 0

    for item in content:
        sanitized = _sanitize_content_item(item)
        if sanitized != item:
            images_replaced += 1
        new_content.append(sanitized)

    return new_content


def _sanitize_nested_content(obj: Any, depth: int = 0) -> Any:
    """Recursively sanitize nested content structures.

    This handles cases where images might be embedded in:
    - Tool results
    - Multi-part responses
    - Nested message structures

    Args:
        obj: Any object that might contain nested image data
        depth: Current recursion depth (max 10 to prevent infinite loops)

    Returns:
        Sanitized object with image data replaced
    """
    if depth > 10:
        return obj

    if isinstance(obj, dict):
        # Check if this is a content item that needs sanitization
        if (
            "type" in obj
            or "inline_data" in obj
            or ("data" in obj and "mime_type" in obj)
        ):
            sanitized = _sanitize_content_item(obj)
            if sanitized != obj:
                return sanitized

        # Recursively process dict values
        result = {}
        for key, value in obj.items():
            result[key] = _sanitize_nested_content(value, depth + 1)
        return result

    elif isinstance(obj, list):
        # Process list items
        return [_sanitize_nested_content(item, depth + 1) for item in obj]

    return obj


def strip_images_from_history(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip image data from conversation history, replacing with placeholders.

    This prevents context explosion when storing conversation history, as
    base64-encoded images can be extremely large and don't need to be resent
    on subsequent turns.

    Args:
        messages: List of conversation messages in any supported format:
            - Responses API format: {"type": "message", "role": "user", "content": [...]}
            - Chat Completions format: {"role": "user", "content": [...]}
            - Gemini format: Messages with inline_data parts

    Returns:
        A new list of messages with image content replaced by placeholders.
        The original messages list is not modified (deep copy is used).
    """
    if not messages:
        return []

    # Deep copy to ensure we never mutate the original messages
    result = copy.deepcopy(messages)
    total_images_replaced = 0

    for msg in result:
        # Get content - could be a list, string, or other structure
        content = msg.get("content")

        if isinstance(content, list):
            # Sanitize content list in-place (we own this copy)
            for i, item in enumerate(content):
                sanitized = _sanitize_content_item(item)
                if sanitized is not item:
                    content[i] = sanitized
                    total_images_replaced += 1

        elif isinstance(content, dict):
            # Content is a single dict - sanitize it
            sanitized = _sanitize_content_item(content)
            if sanitized is not content:
                msg["content"] = sanitized
                total_images_replaced += 1

        # Also check for nested structures in other fields (like tool results)
        for key in ["output", "result", "response", "data"]:
            if key in msg:
                original = msg[key]
                sanitized = _sanitize_nested_content(original)
                if sanitized is not original:
                    msg[key] = sanitized

    if total_images_replaced > 0:
        logger.debug(f"Stripped {total_images_replaced} image(s) from history")

    return result
