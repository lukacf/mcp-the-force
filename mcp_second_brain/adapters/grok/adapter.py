"""Grok adapter implementation using OpenAI-compatible API."""

from typing import Optional, AsyncIterator, Any, Dict, Union, List
import logging
from openai import AsyncOpenAI

from ..base import BaseAdapter
from .errors import AdapterException, ErrorCategory
from ...config import get_settings

logger = logging.getLogger(__name__)

# Model capabilities
GROK_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "grok-3-beta": {
        "context_window": 131_000,
        "supports_functions": True,
        "supports_streaming": True,
        "description": "General purpose Grok 3 model",
    },
    "grok-3-fast": {
        "context_window": 131_000,
        "supports_functions": True,
        "supports_streaming": True,
        "description": "Fast inference with Grok 3",
    },
    "grok-4": {
        "context_window": 256_000,
        "supports_functions": True,
        "supports_streaming": True,
        "description": "Advanced multi-agent reasoning, large documents",
    },
    "grok-4-heavy": {
        "context_window": 256_000,
        "supports_functions": True,
        "supports_streaming": True,
        "description": "Maximum capability (if available)",
    },
    "grok-3-mini": {
        "context_window": 32_000,
        "supports_functions": True,
        "supports_streaming": True,
        "supports_reasoning_effort": True,
        "description": "Quick responses, supports reasoning effort",
    },
    "grok-3-mini-beta": {
        "context_window": 32_000,
        "supports_functions": True,
        "supports_streaming": True,
        "supports_reasoning_effort": True,
        "description": "Beta version of mini model with reasoning effort",
    },
    "grok-3-mini-fast": {
        "context_window": 32_000,
        "supports_functions": True,
        "supports_streaming": True,
        "supports_reasoning_effort": True,
        "description": "Fast mini model with reasoning effort",
    },
}


class GrokAdapter(BaseAdapter):
    """Adapter for xAI Grok models using OpenAI-compatible API."""

    def __init__(self, model_name: Optional[str] = None):
        super().__init__()
        self.model_name = model_name or ""
        settings = get_settings()

        if not settings.xai.api_key:
            raise AdapterException(
                "XAI_API_KEY not configured. Please add your xAI API key to secrets.yaml or set XAI_API_KEY environment variable.",
                error_category=ErrorCategory.CONFIGURATION,
            )

        self.client = AsyncOpenAI(
            api_key=settings.xai.api_key,
            base_url="https://api.x.ai/v1",
        )
        self._supported_models = set(GROK_CAPABILITIES.keys())

        # Set context window if model is specified
        if self.model_name and self.model_name in GROK_CAPABILITIES:
            self.context_window = GROK_CAPABILITIES[self.model_name]["context_window"]
        else:
            # Default to the largest common context window
            self.context_window = 131_000

    async def generate(
        self,
        prompt: str,
        vector_store_ids: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Union[str, Dict[str, Any]]:
        """Generate a response using Grok models.

        Args:
            prompt: Input prompt text
            vector_store_ids: IDs of vector stores to search (unused for Grok)
            **kwargs: Additional parameters including:
                - messages: Pre-formatted messages (overrides prompt)
                - model: Model name (defaults to instance model)
                - temperature: Sampling temperature
                - stream: Whether to stream the response
                - max_tokens: Maximum tokens to generate
                - functions: List of available functions

        Returns:
            Generated text or response dict
        """

        # Get model from kwargs or use instance model
        model = kwargs.get("model", self.model_name)
        if not model:
            raise AdapterException(
                "No model specified",
                error_category=ErrorCategory.INVALID_REQUEST,
            )

        if model not in self._supported_models:
            raise AdapterException(
                f"Model {model} not supported. Choose from: {', '.join(sorted(self._supported_models))}",
                error_category=ErrorCategory.INVALID_REQUEST,
            )

        try:
            # Get messages from kwargs or create from prompt
            messages = kwargs.get("messages")
            if not messages:
                messages = [{"role": "user", "content": prompt}]

            # Get other parameters
            temperature = kwargs.get("temperature", 1.0)
            stream = kwargs.get("stream", False)

            # Build request parameters
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": stream,
            }

            # Add optional parameters
            if "max_tokens" in kwargs:
                request_params["max_tokens"] = kwargs["max_tokens"]

            # Add reasoning_effort for models that support it
            model_capabilities = GROK_CAPABILITIES.get(model, {})
            if (
                model_capabilities.get("supports_reasoning_effort")
                and "reasoning_effort" in kwargs
            ):
                request_params["reasoning_effort"] = kwargs["reasoning_effort"]

            # Handle function calling if provided
            if "functions" in kwargs:
                request_params["tools"] = [
                    {"type": "function", "function": func}
                    for func in kwargs["functions"]
                ]
                if "function_call" in kwargs:
                    request_params["tool_choice"] = kwargs["function_call"]

            # Handle structured output if provided
            if "response_format" in kwargs:
                request_params["response_format"] = kwargs["response_format"]

            logger.info(f"Calling Grok {model} with {len(messages)} messages")

            if stream:
                # For streaming, we need to collect the response
                # since BaseAdapter doesn't support streaming
                full_response = ""
                async for chunk in self._stream_response(request_params):
                    full_response += chunk
                return full_response
            else:
                response = await self.client.chat.completions.create(**request_params)

                # Log token usage if available
                if hasattr(response, "usage") and response.usage:
                    logger.info(
                        f"Grok {model} usage - prompt: {response.usage.prompt_tokens}, "
                        f"completion: {response.usage.completion_tokens}, "
                        f"total: {response.usage.total_tokens}"
                    )

                # Handle function calls
                message = response.choices[0].message
                if hasattr(message, "tool_calls") and message.tool_calls:
                    # Return a dict with function call information
                    logger.info(
                        f"Grok returned {len(message.tool_calls)} function calls"
                    )
                    return {
                        "content": message.content or "",
                        "tool_calls": message.tool_calls,
                        "role": "assistant",
                    }

                return message.content or ""

        except Exception as e:
            error_str = str(e).lower()
            logger.error(f"Grok API error: {str(e)}")

            if "rate" in error_str and "limit" in error_str:
                raise AdapterException(
                    "Rate limit exceeded. Please wait before retrying.",
                    error_category=ErrorCategory.RATE_LIMIT,
                )
            elif any(
                auth_word in error_str
                for auth_word in ["api", "key", "unauthorized", "forbidden"]
            ):
                raise AdapterException(
                    "Invalid API key or unauthorized access. Check your XAI_API_KEY.",
                    error_category=ErrorCategory.AUTHENTICATION,
                )
            elif "not found" in error_str:
                raise AdapterException(
                    f"Model {model} not found. It may not be available via API yet.",
                    error_category=ErrorCategory.INVALID_REQUEST,
                )
            else:
                raise AdapterException(
                    f"Grok API error: {str(e)}", error_category=ErrorCategory.API_ERROR
                )

    async def _stream_response(
        self, request_params: Dict[str, Any]
    ) -> AsyncIterator[str]:
        """Stream response from Grok API.

        Args:
            request_params: Parameters for the API call

        Yields:
            Chunks of generated text
        """
        try:
            # When stream=True, create() returns an AsyncIterator after awaiting
            stream = await self.client.chat.completions.create(**request_params)

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

                # Handle function calls in streaming
                if chunk.choices and chunk.choices[0].delta.tool_calls:
                    # For now, we'll handle function calls in non-streaming mode
                    # This is a limitation we can improve later
                    logger.warning(
                        "Function calls in streaming mode not fully supported yet"
                    )

        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            raise AdapterException(
                f"Streaming failed: {str(e)}", error_category=ErrorCategory.API_ERROR
            )
