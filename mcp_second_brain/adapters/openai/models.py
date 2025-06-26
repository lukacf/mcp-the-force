"""Pydantic models for OpenAI adapter configuration and validation."""

from pydantic import BaseModel, field_validator
from typing import Dict, List, Any, Optional


class ModelCapability(BaseModel):
    """Defines the schema for a single model's capabilities."""

    supports_streaming: bool
    force_background: bool
    supports_web_search: bool = False
    supports_reasoning: bool = False
    supports_parallel_tool_calls: bool = True
    context_window: int = 200000
    default_temperature: Optional[float] = None

    @field_validator("context_window")
    def validate_context_window(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("context_window must be positive")
        return v


# Model capabilities are now defined directly in code using Pydantic models.
# This provides type safety and removes the need for YAML parsing.
model_capabilities: Dict[str, ModelCapability] = {
    "o3": ModelCapability(
        supports_streaming=True,
        force_background=False,
        supports_web_search=False,
        context_window=200000,
        supports_reasoning=True,
        supports_parallel_tool_calls=True,
    ),
    "o3-pro": ModelCapability(
        supports_streaming=False,
        force_background=True,
        supports_web_search=False,
        context_window=200000,
        supports_reasoning=True,
        supports_parallel_tool_calls=True,
    ),
    "gpt-4.1": ModelCapability(
        supports_streaming=True,
        force_background=False,
        supports_web_search=True,
        context_window=1000000,
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
            if not capability.supports_reasoning:
                data.pop("reasoning_effort", None)

            # Remove parallel_tool_calls if not supported
            if not capability.supports_parallel_tool_calls:
                data.pop("parallel_tool_calls", None)

        # Remove internal-only parameters that should not be sent to the API
        data.pop("return_debug", None)
        data.pop("timeout", None)
        data.pop("vector_store_ids", None)

        # Transform messages format if needed
        if "messages" in data:
            data["input"] = data.pop("messages")

        return data
