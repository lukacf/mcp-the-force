"""Grok adapter implementation using OpenAI-compatible API."""

from typing import Optional, AsyncIterator, Any, Dict, Union, List
import logging
import json
from openai import AsyncOpenAI

from ..base import BaseAdapter
from .errors import AdapterException, ErrorCategory
from ...config import get_settings
from ...grok_session_cache import grok_session_cache
from ..tool_handler import ToolHandler

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
        self.tool_handler = ToolHandler()
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

    def _build_search_params(
        self,
        mode: Optional[str],
        custom: Optional[Dict[str, Any]],
        return_citations: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Build search parameters for Grok Live Search.

        Args:
            mode: Search mode - 'auto', 'on', 'off', or None
            custom: Custom search parameters to merge
            return_citations: Whether to return source citations

        Returns:
            Search parameters dict or None if search is disabled
        """
        if mode is None:  # User did not ask for search → keep legacy behavior
            return None
        if mode not in {"auto", "on", "off"}:
            raise ValueError("search_mode must be 'auto', 'on', or 'off'")

        # Start with minimal defaults for low latency
        params: Dict[str, Any] = {"mode": mode, "returnCitations": return_citations}

        if custom:  # Allow power users to inject full spec
            params.update(custom)

        return params

    def _snake_case_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Convert camelCase keys to snake_case names that xAI backend expects."""
        mapping = {
            "returnCitations": "return_citations",
            "fromDate": "from_date",
            "toDate": "to_date",
            "maxSearchResults": "max_search_results",
            "allowedWebsites": "allowed_websites",
            "excludedWebsites": "excluded_websites",
            "safeSearch": "safe_search",
            "xHandles": "x_handles",
        }
        out = {}
        for k, v in params.items():
            nk = mapping.get(k, k)  # fall back to same key if already snake_case
            if v is not None:
                out[nk] = v
        return out

    def _normalize_source(self, src: Any) -> Dict[str, Any]:
        """Normalize a source citation to a consistent dict format."""
        if isinstance(src, dict):
            return src
        if isinstance(src, str):
            return {"url": src}
        # fallback – make debugging easier
        return {"raw": str(src)}

    def _extract_sources(self, response: Any) -> List[Dict[str, Any]]:
        """Extract and normalize sources from xAI response."""
        # Native xai-sdk exposes resp.sources directly
        sources = getattr(response, "sources", None)

        # OpenAI client: extras live in model_extra
        if sources is None and hasattr(response, "model_extra"):
            extra = response.model_extra
            sources = extra.get("sources") or extra.get("citations")

        if not sources:
            return []

        return [self._normalize_source(s) for s in sources]

    async def generate(
        self,
        prompt: str,
        vector_store_ids: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Union[str, Dict[str, Any]]:
        """Generate a response using Grok models with session management and tool execution.

        Args:
            prompt: Input prompt text
            vector_store_ids: IDs of vector stores to search
            **kwargs: Additional parameters including:
                - session_id: Session ID for conversation history
                - messages: Pre-formatted messages (overrides prompt)
                - model: Model name (defaults to instance model)
                - temperature: Sampling temperature
                - stream: Whether to stream the response
                - max_tokens: Maximum tokens to generate
                - functions: List of available functions

        Returns:
            Generated text response
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
            session_id = kwargs.get("session_id")

            # New turn constructed by the executor (system + user)
            incoming_msgs = kwargs.get("messages") or [
                {"role": "user", "content": prompt}
            ]

            # --- SESSION CONTINUITY FIX ---
            messages = incoming_msgs
            if session_id:
                previous = await grok_session_cache.get_history(session_id)
                if previous:
                    # Avoid duplicating the system / developer prompt
                    if (
                        previous
                        and incoming_msgs
                        and previous[0].get("role") == "system"
                        and incoming_msgs[0].get("role") == "system"
                        and previous[0].get("content")
                        == incoming_msgs[0].get("content")
                    ):
                        incoming_msgs = incoming_msgs[1:]
                    messages = previous + incoming_msgs

            # Get other parameters
            temperature = kwargs.get("temperature", 1.0)
            stream = kwargs.get("stream", False)

            # Extract search parameters (use get() to avoid modifying kwargs)
            search_mode = kwargs.get("search_mode", None)
            search_parameters = kwargs.get("search_parameters", None)
            return_citations = kwargs.get("return_citations", True)

            # Build search parameters
            search_params = self._build_search_params(
                mode=search_mode,
                custom=search_parameters,
                return_citations=return_citations,
            )

            # Build base request parameters
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": stream,
            }

            # Add search parameters via extra_body to bypass OpenAI SDK validation
            if search_params:
                search_params_snake = self._snake_case_params(search_params)
                request_params["extra_body"] = {
                    "search_parameters": search_params_snake
                }
                logger.info(f"Added Grok Live Search parameters: {search_params_snake}")

            # Add optional parameters (filter out our custom search parameters)
            if "max_tokens" in kwargs:
                request_params["max_tokens"] = kwargs["max_tokens"]

            # Filter out search parameters from kwargs to avoid passing them to OpenAI
            filtered_kwargs = {
                k: v
                for k, v in kwargs.items()
                if k not in {"search_mode", "search_parameters", "return_citations"}
            }

            # Add reasoning_effort for models that support it
            model_capabilities = GROK_CAPABILITIES.get(model, {})
            if (
                model_capabilities.get("supports_reasoning_effort")
                and "reasoning_effort" in filtered_kwargs
            ):
                request_params["reasoning_effort"] = filtered_kwargs["reasoning_effort"]

            # Handle function calling - combine custom tools with built-in tools
            custom_tools = []
            if "functions" in filtered_kwargs:
                custom_tools = [
                    {"type": "function", "function": func}
                    for func in filtered_kwargs["functions"]
                ]

            # Get built-in tools using ToolHandler (this fixes the attachment bug)
            disable_memory_search = kwargs.get("disable_memory_search", False)
            built_in_tool_declarations = self.tool_handler.prepare_tool_declarations(
                adapter_type="grok",
                vector_store_ids=vector_store_ids,
                disable_memory_search=disable_memory_search,
            )

            # Wrap built-in tools in the format Grok expects
            built_in_tools = [
                {"type": "function", "function": tool}
                for tool in built_in_tool_declarations
            ]

            # Combine all tools
            all_tools = custom_tools + built_in_tools
            if all_tools:
                request_params["tools"] = all_tools
                if "function_call" in filtered_kwargs:
                    request_params["tool_choice"] = filtered_kwargs["function_call"]

            # Handle structured output if provided
            if "response_format" in filtered_kwargs:
                request_params["response_format"] = filtered_kwargs["response_format"]

            logger.info(f"Calling Grok {model} with {len(messages)} messages")
            logger.debug(f"Final request params: {request_params}")

            # --- TOOL EXECUTION LOOP ---
            while True:
                try:
                    response = await self.client.chat.completions.create(
                        **request_params
                    )
                    logger.debug(f"RAW xAI response: {response.model_dump()}")
                except Exception:
                    logger.exception(
                        f"xAI API call failed with search_mode={search_mode}"
                    )
                    raise
                message = response.choices[0].message

                # Log token usage if available
                if hasattr(response, "usage") and response.usage:
                    logger.info(
                        f"Grok {model} usage - prompt: {response.usage.prompt_tokens}, "
                        f"completion: {response.usage.completion_tokens}, "
                        f"total: {response.usage.total_tokens}"
                    )

                messages.append(message.model_dump(exclude_none=True))

                if not message.tool_calls:
                    break  # Exit loop if no more tool calls

                tool_results = []
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    try:
                        # Use ToolHandler for centralized tool execution
                        output = await self.tool_handler.execute_tool_call(
                            tool_name=tool_name,
                            tool_args=tool_args,
                            vector_store_ids=vector_store_ids,
                        )
                    except Exception as e:
                        output = f"Error executing tool '{tool_name}': {e}"
                        logger.error(f"Tool execution error: {e}")

                    tool_results.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": tool_name,
                            "content": str(output),
                        }
                    )

                messages.extend(tool_results)
                request_params["messages"] = messages

            # --- SAVE HISTORY AND RETURN ---
            if session_id:
                await grok_session_cache.set_history(session_id, messages)

            final_message = messages[-1]
            content = final_message.get("content") or ""

            # Extract and normalize sources/citations from Live Search
            sources = self._extract_sources(response)

            # Only return dict format when we actually have sources
            if sources:
                return {"content": content, "sources": sources}

            # Return plain text for backward compatibility
            return content

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
