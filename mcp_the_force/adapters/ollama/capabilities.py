"""Capabilities definition for Ollama models."""

from dataclasses import dataclass
from typing import Optional

from ..capabilities import AdapterCapabilities


@dataclass
class OllamaCapabilities(AdapterCapabilities):
    """Capabilities for Ollama local models."""

    provider: str = "ollama"
    model_family: str = "local_llm"
    model_name: str = ""

    # Most Ollama models support these features
    supports_tools: bool = True  # Note: quality varies by model
    supports_streaming: bool = True
    supports_temperature: bool = True
    supports_structured_output: bool = (
        False  # Local models don't support schema validation
    )
    supports_reasoning: bool = False  # Most local models don't have reasoning mode
    supports_vision: bool = False  # Depends on model, conservative default
    supports_prefill: bool = False
    supports_computer_use: bool = False
    supports_web_search: bool = False  # Local models can't search
    supports_n: bool = False
    supports_stop_sequences: bool = True

    # Context window - will be set dynamically from config or discovery
    max_context_window: int = 16384

    # Local models don't have built-in vector stores
    native_vector_store_provider: Optional[str] = None

    # Pricing - local models are free to run
    # (but have hardware/electricity costs)
    price_per_million_input_tokens: float = 0.0
    price_per_million_output_tokens: float = 0.0

    def __post_init__(self):
        """Extract model family from model name if not set."""
        if not self.model_family and self.model_name:
            # Extract family from model name (e.g., "llama3:latest" -> "llama3")
            self.model_family = self.model_name.split(":")[0]
