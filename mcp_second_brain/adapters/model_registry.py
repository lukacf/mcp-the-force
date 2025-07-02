"""Central registry for model information across all adapters."""


def get_model_context_window(model: str) -> int:
    """Get context window for any model across all adapters.

    Args:
        model: Model name (e.g., "o3", "gemini-2.5-pro")

    Returns:
        Context window size in tokens, with conservative fallback
    """
    # Try OpenAI models first
    from .openai.models import get_context_window as get_openai_window
    from .openai.models import model_capabilities

    if model in model_capabilities:
        return get_openai_window(model)

    # Try Vertex/Gemini models
    from .vertex.models import get_context_window as get_vertex_window
    from .vertex.models import model_capabilities as vertex_capabilities

    if model in vertex_capabilities:
        return get_vertex_window(model)

    # Conservative fallback for unknown models
    return 32_000
