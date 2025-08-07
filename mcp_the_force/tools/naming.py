"""Utilities for sanitizing and normalizing tool names for MCP compliance."""

import re


def sanitize_tool_name(name: str, prefix: str = "", max_length: int = 128) -> str:
    """
    Sanitize a name to be MCP-compliant tool name.

    MCP tool names must match: ^[a-zA-Z0-9_]{1,128}$

    Args:
        name: The raw name to sanitize
        prefix: Optional prefix to add (e.g., "chat_with_")
        max_length: Maximum length for the final tool name (default: 128 for MCP)

    Returns:
        Sanitized tool name that complies with MCP naming requirements

    Examples:
        >>> sanitize_tool_name("llama3:latest", "chat_with_")
        "chat_with_llama3_latest"
        >>> sanitize_tool_name("gpt-4o", "chat_with_")
        "chat_with_gpt_4o"
        >>> sanitize_tool_name("model.v1.2:123b", "chat_with_")
        "chat_with_model_v1_2_123b"
    """
    if not name:
        raise ValueError("Name cannot be empty")

    # Replace all non-alphanumeric characters (except existing underscores) with underscores
    # This handles colons, dots, spaces, hyphens, and any other special characters
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)

    # Remove consecutive underscores and leading/trailing underscores
    safe_name = re.sub(r"_+", "_", safe_name).strip("_")

    # Ensure it starts with a letter (prepend 'm' if it starts with a number)
    if safe_name and safe_name[0].isdigit():
        safe_name = f"m{safe_name}"

    # Build the final tool name with prefix
    tool_name = f"{prefix}{safe_name}" if prefix else safe_name

    # Truncate if longer than max_length
    if len(tool_name) > max_length:
        if prefix:
            # Keep the prefix and truncate the model part
            max_name_len = max_length - len(prefix)
            safe_name = safe_name[:max_name_len].rstrip("_")
            tool_name = f"{prefix}{safe_name}"
        else:
            tool_name = tool_name[:max_length].rstrip("_")

    # Final validation
    if not tool_name:
        raise ValueError("Sanitized name resulted in empty string")

    if not re.match(r"^[a-zA-Z0-9_]{1,128}$", tool_name):
        raise ValueError(f"Sanitized name '{tool_name}' does not match MCP pattern")

    return tool_name


def model_to_chat_tool_name(model_name: str) -> str:
    """
    Convert model name to valid chat tool name.

    Args:
        model_name: The model name to convert

    Returns:
        Tool name in format "chat_with_{sanitized_model_name}"
    """
    return sanitize_tool_name(model_name, "chat_with_")


def model_to_research_tool_name(model_name: str) -> str:
    """
    Convert model name to valid research tool name.

    Args:
        model_name: The model name to convert

    Returns:
        Tool name in format "research_with_{sanitized_model_name}"
    """
    return sanitize_tool_name(model_name, "research_with_")
