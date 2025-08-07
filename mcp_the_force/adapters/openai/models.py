"""OpenAI request models and validation.

This module defines the request validation and API formatting logic.
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field


class OpenAIRequest(BaseModel):
    """Validated request parameters for OpenAI Responses API."""

    model: str
    input: Union[str, List[Dict[str, Any]]]
    instructions: Optional[str] = None
    previous_response_id: Optional[str] = None
    stream: bool = False
    background: bool = False
    # This field is now internal and will be transformed into the 'reasoning' dict.
    reasoning_effort: Optional[str] = Field(default=None, exclude=True)
    temperature: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    parallel_tool_calls: bool = Field(default=True, alias="parallel_tool_calls")

    # Internal fields not sent to OpenAI API
    vector_store_ids: Optional[List[str]] = Field(default=None, exclude=True)
    structured_output_schema: Optional[Dict[str, Any]] = Field(
        default=None, exclude=True
    )
    disable_history_search: bool = Field(default=False, exclude=True)
    return_debug: bool = Field(default=False, exclude=True)
    max_output_tokens: Optional[int] = Field(default=None, exclude=True)
    timeout: float = Field(default=300.0, exclude=True)

    def to_api_format(self) -> Dict[str, Any]:
        """Convert to OpenAI API format, handling nested reasoning and structured outputs."""
        # The `reasoning_effort` field is now excluded by `exclude=True` in its definition
        api_data = self.model_dump(by_alias=True, exclude_none=True)

        # Manually construct the 'reasoning' parameter if effort is specified.
        if self.reasoning_effort:
            # Check if the model actually supports it to avoid sending invalid params.
            from .definitions import get_model_capability

            capability = get_model_capability(self.model)
            if capability and capability.supports_reasoning_effort:
                api_data["reasoning"] = {"effort": self.reasoning_effort}

        # Include structured output schema if provided
        # The actual schema transformation will be done in flow.py
        if self.structured_output_schema:
            api_data["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "structured_output",
                    "schema": self.structured_output_schema,
                }
            }

        return api_data  # type: ignore[no-any-return]
