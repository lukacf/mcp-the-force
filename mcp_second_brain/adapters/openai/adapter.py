"""OpenAI adapter - main entry point.

This module assembles all the refactored components into the final adapter
that implements the BaseAdapter interface.
"""

import logging
from typing import Any, Dict, List, Optional

from mcp_second_brain.adapters.base import BaseAdapter
from .errors import AdapterException, ErrorCategory
from .flow import FlowOrchestrator
from .models import OpenAIRequest, model_capabilities


logger = logging.getLogger(__name__)


class OpenAIAdapter(BaseAdapter):
    """Adapter for OpenAI models using the Responses API.

    This adapter supports:
    - OpenAI o-series models (o3, o3-pro, o4-mini)
    - GPT-4.1 with web search capabilities
    - Streaming and background execution modes
    - Bounded concurrent tool execution
    - Process-safe client management
    """

    def __init__(self, model: str):
        """Initialize the OpenAI adapter.

        Args:
            model: Model name (unused, kept for compatibility with factory)
        """
        # Get API key from settings
        from mcp_second_brain.config import get_settings

        settings = get_settings()
        self._api_key = settings.openai_api_key
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        # Set model_name for base class compatibility
        self.model_name = model

        # Load model capabilities and set required attributes for BaseAdapter
        if self.model_name in model_capabilities:
            capabilities = model_capabilities[self.model_name]
            self.context_window = capabilities.context_window
            self.description_snippet = (
                f"OpenAI {self.model_name}: "
                f"{capabilities.context_window:,} token context"
            )
        else:
            # Fallback for unknown models or when capabilities not loaded
            logger.warning(
                f"Model '{self.model_name}' capabilities not found, using defaults"
            )
            self.context_window = 200_000  # Conservative default
            self.description_snippet = f"OpenAI {self.model_name}"

    async def generate(
        self,
        prompt: str,
        vector_store_ids: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate a response using OpenAI's Responses API.

        Args:
            prompt: Input prompt text
            vector_store_ids: IDs of vector stores to search
            **kwargs: Additional parameters including:
                - messages: Pre-formatted messages (overrides prompt)
                - model: Model name (defaults to instance model)
                - tool_dispatcher: Function to execute tools
                - max_output_tokens: Maximum tokens to generate
                - temperature: Sampling temperature
                - tools: List of available tools
                - reasoning_effort: Reasoning effort level for o-series models
                - timeout: Request timeout in seconds
                - previous_response_id: ID for continuing conversations
                - return_debug: Include debug information

        Returns:
            Response dictionary with content and metadata

        Raises:
            AdapterException: If the request fails
        """
        try:
            # Extract parameters from kwargs
            messages = kwargs.pop("messages", None)
            if messages is None:
                # Convert prompt to messages format
                messages = [{"role": "user", "content": prompt}]

            model = kwargs.pop("model", self.model_name)
            tool_dispatcher = kwargs.pop("tool_dispatcher", None)
            max_output_tokens = kwargs.pop("max_output_tokens", None)
            temperature = kwargs.pop("temperature", None)
            tools = kwargs.pop("tools", None)
            reasoning_effort = kwargs.pop("reasoning_effort", None)

            # Build request parameters
            request_params = {
                "model": model,
                "messages": messages,
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
                "tools": tools,
                "reasoning_effort": reasoning_effort,
                "vector_store_ids": vector_store_ids,
                "_api_key": self._api_key,  # Pass API key for client creation
                **kwargs,  # Include all additional parameters
            }

            # Create request object (validates and applies defaults)
            request = OpenAIRequest(**request_params)

            # Preserve caller-supplied session_id (if any) – it is *not* part of
            # the OpenAIRequest schema, so we must attach it manually.
            request_data = request.model_dump(exclude_none=True)
            if "session_id" in kwargs:
                request_data["session_id"] = kwargs["session_id"]

            # Create and run flow orchestrator
            orchestrator = FlowOrchestrator(tool_dispatcher=tool_dispatcher)

            return await orchestrator.run(request_data)

        except AdapterException:
            # Re-raise our own errors
            raise
        except Exception as e:
            # Wrap unexpected errors
            logger.error(f"Unexpected error in OpenAI adapter: {e}", exc_info=True)
            raise AdapterException(
                category=ErrorCategory.FATAL_CLIENT,
                message=f"Unexpected error: {str(e)}",
            )
