"""Pydantic models for OpenAI adapter configuration and validation."""

from pydantic import BaseModel, field_validator, model_validator
from typing import Dict, List, Any, Optional


class ModelCapability(BaseModel):
    """Defines the schema for a single model's capabilities."""

    supports_streaming: bool
    force_background: bool
    supports_web_search: bool = False
    web_search_tool: str = "web_search"  # Tool name for web search
    supports_custom_tools: bool = True  # Whether model supports custom tools
    supports_reasoning: bool = False
    supports_reasoning_effort: bool = (
        False  # Whether model supports reasoning_effort parameter
    )
    supports_parallel_tool_calls: bool = True
    context_window: int = 200000
    default_temperature: Optional[float] = None
    default_reasoning_effort: Optional[str] = (
        None  # Default reasoning effort for models that support it
    )

    @field_validator("context_window")
    def validate_context_window(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("context_window must be positive")
        return v

    @model_validator(mode="after")
    def validate_reasoning_temperature_exclusion(self) -> "ModelCapability":
        """Ensure models with reasoning support don't have temperature and vice versa."""
        if self.supports_reasoning and self.default_temperature is not None:
            raise ValueError(
                "Models with reasoning support should not have a default_temperature"
            )
        return self


# Model capabilities are now defined directly in code using Pydantic models.
# This provides type safety and removes the need for YAML parsing.
model_capabilities: Dict[str, ModelCapability] = {
    "o3": ModelCapability(
        supports_streaming=True,
        force_background=False,
        supports_web_search=True,  # Now supports web search!
        context_window=200000,
        supports_reasoning=True,
        supports_reasoning_effort=True,  # Regular o3 supports reasoning_effort
        default_reasoning_effort="medium",
        supports_parallel_tool_calls=True,
    ),
    "o3-pro": ModelCapability(
        supports_streaming=False,
        force_background=True,
        supports_web_search=True,  # Now supports web search!
        context_window=200000,
        supports_reasoning=True,
        supports_reasoning_effort=True,  # Regular o3-pro supports reasoning_effort
        default_reasoning_effort="high",
        supports_parallel_tool_calls=True,
    ),
    "gpt-4.1": ModelCapability(
        supports_streaming=True,
        force_background=False,
        supports_web_search=True,
        context_window=1000000, # GPT-4.1 has a context window of 1M tokens (May 2025)
        supports_reasoning=False,
        supports_parallel_tool_calls=True,
    ),
    "o4-mini": ModelCapability(
        supports_streaming=True,
        force_background=False,
        supports_web_search=False,
        context_window=200000,
        supports_reasoning=False,
        supports_parallel_tool_calls=True,
    ),
    # New deep research models
    "o3-deep-research": ModelCapability(
        supports_streaming=False,
        force_background=True,
        supports_web_search=True,
        web_search_tool="web_search_preview",  # Deep research uses preview
        supports_custom_tools=False,  # Deep research models don't support custom tools
        context_window=200000,
        supports_reasoning=True,
        supports_reasoning_effort=False,  # Deep research models don't support reasoning_effort
        default_reasoning_effort="high",  # Will be ignored, but kept for consistency
        supports_parallel_tool_calls=True,
    ),
    "o4-mini-deep-research": ModelCapability(
        supports_streaming=False,  # Deep research models don't support streaming
        force_background=True,  # Deep research models must use background mode
        supports_web_search=True,
        web_search_tool="web_search_preview",  # Deep research uses preview
        supports_custom_tools=False,  # Deep research models don't support custom tools
        context_window=200000,
        supports_reasoning=True,
        supports_reasoning_effort=False,  # Deep research models don't support reasoning_effort
        default_reasoning_effort="medium",  # Will be ignored, but kept for consistency
        supports_parallel_tool_calls=True,
    ),
}


class OpenAIRequest(BaseModel):
    """Validated request parameters for OpenAI API calls."""

    model: str
    messages: List[Dict[str, Any]]
    stream: bool = False
    background: bool = False
    reasoning_effort: Optional[str] = None
    temperature: Optional[float] = None
    previous_response_id: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    parallel_tool_calls: Optional[bool] = None
    timeout: float = 300.0  # Default timeout in seconds
    vector_store_ids: Optional[List[str]] = None
    return_debug: bool = False
    structured_output_schema: Optional[Dict[str, Any]] = None
    disable_memory_search: bool = False

    @field_validator("model")
    def model_is_defined(cls, v: str) -> str:
        """Ensure the model exists in our capabilities."""
        if v not in model_capabilities:
            raise ValueError(
                f"Model '{v}' is not defined in model_capabilities. "
                f"Available models: {list(model_capabilities.keys())}"
            )
        return v

    @field_validator("stream")
    def validate_stream_capability(cls, v: bool, values) -> bool:
        """Ensure streaming is only used with capable models."""
        if not v:
            return v

        model_name = values.data.get("model")
        if model_name:
            capability = model_capabilities.get(model_name)
            if capability and not capability.supports_streaming:
                raise ValueError(
                    f"Model '{model_name}' does not support streaming. "
                    "Please use background mode instead."
                )
        return v

    @field_validator("reasoning_effort")
    def validate_reasoning_support(cls, v: Optional[str], values) -> Optional[str]:
        """Ensure reasoning parameters are only used with capable models."""
        if not v:
            return v

        model_name = values.data.get("model")
        if model_name:
            capability = model_capabilities.get(model_name)
            if capability and not capability.supports_reasoning:
                raise ValueError(
                    f"Model '{model_name}' does not support reasoning parameters."
                )
        return v

    def to_api_format(self) -> Dict[str, Any]:
        """Prepares the request for the OpenAI SDK, stripping unsupported fields.

        Returns:
            Dictionary ready for the OpenAI API call.
        """
        data: Dict[str, Any] = self.model_dump(exclude_none=True)

        capability = model_capabilities.get(self.model)
        if capability:
            # Remove reasoning if not supported
            if (
                not capability.supports_reasoning
                or not capability.supports_reasoning_effort
            ):
                data.pop("reasoning_effort", None)

            # Remove temperature if model supports reasoning (reasoning models don't support temperature)
            if capability.supports_reasoning:
                data.pop("temperature", None)

            # Remove parallel_tool_calls if not supported
            if not capability.supports_parallel_tool_calls:
                data.pop("parallel_tool_calls", None)

        # Remove internal-only parameters that should not be sent to the API
        data.pop("return_debug", None)
        data.pop("timeout", None)
        data.pop("vector_store_ids", None)
        data.pop("disable_memory_search", None)

        # Handle structured output schema
        if "structured_output_schema" in data:
            schema = data.pop("structured_output_schema")
            data["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "structured_response",  # Required by OpenAI API
                    "schema": schema,
                    "strict": True,
                }
            }

        # Transform messages format if needed
        if "messages" in data:
            data["input"] = data.pop("messages")

        return data


def get_context_window(model: str) -> int:
    """Get context window for a model, with fallback."""
    capability = model_capabilities.get(model)
    if capability:
        return capability.context_window
    return 32_000  # Conservative fallback for unknown models
