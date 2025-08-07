"""Parameters for Ollama tools."""

from typing import Optional

from ..params import BaseToolParams
from ...tools.descriptors import Route


class OllamaToolParams(BaseToolParams):
    """Parameters for Ollama model tools."""

    temperature: float = Route.adapter(
        default=0.7,
        description="Sampling temperature (0.0-2.0). Lower values are more deterministic.",
    )

    max_tokens: Optional[int] = Route.adapter(
        default=1024, description="Maximum tokens to generate. None for model default."
    )

    keep_alive: Optional[str] = Route.adapter(
        default=None,
        description="How long to keep model loaded (e.g. '5m', '2h', '-1' for indefinite)",
    )

    format: Optional[str] = Route.adapter(
        default=None, description="Response format. Use 'json' for JSON mode."
    )

    seed: Optional[int] = Route.adapter(
        default=None, description="Random seed for reproducible outputs"
    )

    top_p: Optional[float] = Route.adapter(
        default=None, description="Nucleus sampling threshold (0.0-1.0)"
    )

    top_k: Optional[int] = Route.adapter(
        default=None, description="Top-k sampling parameter"
    )

    repeat_penalty: Optional[float] = Route.adapter(
        default=None, description="Penalty for repeating tokens (1.0 = no penalty)"
    )


# Note: structured_output_schema not supported by Ollama models
# Use the 'format' parameter with 'json' for basic JSON mode instead

# Note: num_ctx is handled dynamically based on configuration and memory
# Users shouldn't need to set this directly
