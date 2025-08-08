"""Utility to format model capabilities into readable descriptions."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..adapters.capabilities import AdapterCapabilities


def format_capabilities(capabilities: "AdapterCapabilities") -> str:
    """Format model capabilities into a readable string.

    Args:
        capabilities: The model's capability instance

    Returns:
        A formatted string describing the model's capabilities
    """
    # Collect capability features
    features = []

    # Context window
    if capabilities.max_context_window:
        # Format large numbers nicely
        tokens = capabilities.max_context_window
        if tokens >= 1_000_000:
            context_str = f"{tokens // 1_000_000}M"
        elif tokens >= 1_000:
            context_str = f"{tokens // 1_000}k"
        else:
            context_str = str(tokens)
        features.append(f"context: {context_str} tokens")

    # Core capabilities
    capability_list = []

    if capabilities.supports_tools:
        capability_list.append("tools")

    if capabilities.supports_web_search:
        capability_list.append("web search")
    elif capabilities.supports_live_search:
        capability_list.append("Live Search (X/Twitter)")

    if capabilities.supports_reasoning_effort:
        capability_list.append("reasoning effort")

    if capabilities.supports_vision:
        capability_list.append("multimodal (vision)")

    if capabilities.supports_temperature:
        capability_list.append("temperature control")

    if capabilities.supports_structured_output:
        capability_list.append("structured output")

    # Parallel function calls
    if capabilities.parallel_function_calls:
        if capabilities.parallel_function_calls == -1:
            capability_list.append("parallel function calls")
        else:
            capability_list.append(
                f"parallel function calls (max {capabilities.parallel_function_calls})"
            )

    if capability_list:
        features.append(f"capabilities: {', '.join(capability_list)}")

    # Special cases for research models
    if hasattr(capabilities, "force_background") and capabilities.force_background:
        features.append("runtime: asynchronous")

    # Output tokens for Anthropic models
    if hasattr(capabilities, "max_output_tokens") and capabilities.max_output_tokens:
        tokens = capabilities.max_output_tokens
        if tokens >= 1_000:
            output_str = f"{tokens // 1_000}k"
        else:
            output_str = str(tokens)
        features.append(f"max output: {output_str} tokens")

    return " | ".join(features) if features else ""
