from typing import Any, List, Optional, Dict
import asyncio
import logging
import threading
import time
from google import genai
from google.genai import types
from google.genai.types import HarmCategory, HarmBlockThreshold
from ...config import get_settings
from ..base import BaseAdapter
from ..memory_search_declaration import create_search_memory_declaration_gemini
from ..attachment_search_declaration import create_attachment_search_declaration_gemini
from ...gemini_session_cache import gemini_session_cache

# Removed validation imports - no longer validating structured output
# from ...utils.validation import validate_json_schema
# from jsonschema import ValidationError
from .models import model_capabilities

logger = logging.getLogger(__name__)

# Thread-safe singleton implementation
_client: Optional[genai.Client] = None
_client_lock = threading.Lock()


def get_client():
    """Get the shared Vertex AI client instance (thread-safe singleton)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                settings = get_settings()
                if not settings.vertex_project or not settings.vertex_location:
                    raise ValueError(
                        "VERTEX_PROJECT and VERTEX_LOCATION must be configured"
                    )
                _client = genai.Client(
                    vertexai=True,
                    project=settings.vertex_project,
                    location=settings.vertex_location,
                )
    return _client


class VertexAdapter(BaseAdapter):
    def __init__(self, model: str):
        self.model_name = model

        # Load model capabilities
        capability = model_capabilities.get(self.model_name)
        if capability:
            self.context_window = capability.context_window
            self.description_snippet = (
                f"Gemini {self.model_name}: "
                f"{capability.context_window:,} token context, "
                f"{capability.max_thinking_budget:,} thinking budget"
            )
        else:
            # Fallback for unknown models
            logger.warning(
                f"Model '{self.model_name}' capabilities not found, using defaults"
            )
            self.context_window = 2_000_000
            self.description_snippet = (
                "Deep multimodal reasoner"
                if "pro" in model
                else "Flash summary sprinter"
            )

    def _extract_text_from_parts(self, parts: List[Any]) -> str:
        """Extract text from response parts, handling both text and inline_data."""
        response_text = ""
        for part in parts:
            if getattr(part, "text", None):
                response_text += part.text
            elif getattr(part, "inline_data", None):
                # Handle JSON responses returned as inline_data
                if part.inline_data.mime_type == "application/json":
                    response_text += part.inline_data.data.decode("utf-8")
        return response_text

    async def _generate_async(self, client, **kwargs):
        """Async wrapper for synchronous generate_content calls."""
        try:
            logger.info(
                f"[ADAPTER] Starting Vertex generate_content at {time.strftime('%H:%M:%S')}"
            )
            api_start_time = time.time()
            result = await asyncio.to_thread(client.models.generate_content, **kwargs)
            api_end_time = time.time()
            logger.info(
                f"[ADAPTER] Vertex generate_content completed in {api_end_time - api_start_time:.2f}s"
            )
            return result
        except asyncio.CancelledError:
            logger.info("[ADAPTER] Vertex generate_content cancelled by user")
            raise

    async def generate(
        self,
        prompt: str,
        vector_store_ids: List[str] | None = None,
        max_reasoning_tokens: int | None = None,
        reasoning_effort: str | None = None,
        temperature: float | None = None,
        return_debug: bool = False,
        messages: Optional[List[Dict[str, str]]] = None,
        system_instruction: Optional[str] = None,
        structured_output_schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        self._ensure(prompt)

        # --- NEW SESSION HANDLING ---
        session_id = kwargs.get("session_id")

        # Always start with loading session history if available
        history = []
        if session_id:
            history = await gemini_session_cache.get_history(session_id)
            logger.info(f"Loaded {len(history)} messages from session {session_id}")

        # Add the current user prompt to the history
        # The prompt is now small on subsequent turns due to stable-list logic
        contents = history + [
            types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        ]

        # Configure safety settings
        safety_settings = [
            types.SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=HarmBlockThreshold.OFF,
            ),
            types.SafetySetting(
                category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=HarmBlockThreshold.OFF,
            ),
            types.SafetySetting(
                category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=HarmBlockThreshold.OFF,
            ),
            types.SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=HarmBlockThreshold.OFF,
            ),
        ]

        # Setup tools - always include search_project_memory
        function_declarations = []

        # Always add search_project_memory for accessing memory
        memory_search_decl = create_search_memory_declaration_gemini()
        function_declarations.append(memory_search_decl)

        # Add attachment search tool when vector stores are provided
        if vector_store_ids:
            logger.info(
                f"Registering search_session_attachments for {len(vector_store_ids)} vector stores"
            )
            attachment_search_decl = create_attachment_search_declaration_gemini()
            function_declarations.append(attachment_search_decl)

        # Build tools list
        tools: Optional[List[Any]] = None
        if function_declarations:
            tools = [types.Tool(function_declarations=function_declarations)]

        # Build config with explicit parameters
        settings = get_settings()
        max_tokens = settings.vertex.max_output_tokens or 65535

        # Build base config
        config_kwargs = {
            "temperature": temperature or settings.default_temperature,
            "top_p": 0.95,
            "max_output_tokens": max_tokens,
            "safety_settings": safety_settings,
            "tools": tools,
        }

        # Add response_schema for structured output
        if structured_output_schema:
            config_kwargs["response_schema"] = structured_output_schema
            # Response schema requires JSON mime type
            config_kwargs["response_mime_type"] = "application/json"
            # Ensure the model is prompted for JSON when using response_schema
            if not system_instruction:
                system_instruction = "Your response must be a valid JSON object conforming to the provided schema."
            else:
                system_instruction += "\nYour response must be a valid JSON object conforming to the provided schema."

        # Add system instruction if provided
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        # Get model capability once
        capability = model_capabilities.get(self.model_name)

        # Add thinking config for models that support it
        # Map reasoning_effort to max_reasoning_tokens if not explicitly set
        if reasoning_effort and not max_reasoning_tokens:
            if capability and capability.supports_thinking_budget:
                # Use the reasoning map from the model's capability
                max_reasoning_tokens = capability.reasoning_effort_map.get(
                    reasoning_effort
                )
                if max_reasoning_tokens is None:
                    logger.warning(
                        f"Unknown reasoning_effort '{reasoning_effort}' for {self.model_name}. "
                        f"Falling back to medium."
                    )
                    # Fallback to medium if an invalid effort is provided
                    max_reasoning_tokens = capability.reasoning_effort_map.get("medium")
            else:
                logger.warning(
                    f"Model {self.model_name} not found in capabilities or does not support thinking budget. "
                    f"Cannot apply reasoning_effort."
                )

        # Add thinking config for models that support reasoning
        if capability and capability.supports_thinking_budget and max_reasoning_tokens:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=max_reasoning_tokens if max_reasoning_tokens > 0 else -1
            )

        generate_content_config = types.GenerateContentConfig(**config_kwargs)

        # Generate response
        client = get_client()
        try:
            response = await self._generate_async(
                client,
                model=self.model_name,
                contents=contents,
                config=generate_content_config,
            )
        except Exception as e:
            import google.api_core.exceptions
            from .errors import AdapterException, ErrorCategory

            # Handle specific Google API errors
            if isinstance(e, google.api_core.exceptions.ResourceExhausted):
                raise AdapterException(
                    "Rate limit exceeded. Please try again later.",
                    error_category=ErrorCategory.RATE_LIMIT,
                    original_error=e,
                )
            elif isinstance(e, google.api_core.exceptions.InvalidArgument):
                raise AdapterException(
                    f"Invalid request: {str(e)}",
                    error_category=ErrorCategory.INVALID_REQUEST,
                    original_error=e,
                )
            elif isinstance(e, google.api_core.exceptions.ServiceUnavailable):
                raise AdapterException(
                    "Service temporarily unavailable. Please retry.",
                    error_category=ErrorCategory.TRANSIENT_ERROR,
                    original_error=e,
                )
            else:
                # Generic error handling as last resort
                logger.error(
                    f"Vertex AI API call failed for model {self.model_name}: {type(e).__name__}: {str(e)}",
                    exc_info=True,
                    extra={
                        "model": self.model_name,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "project": getattr(client, "_project_id", "unknown"),
                    },
                )
                raise

        final_response_content = ""

        # Handle function calls if any
        if (
            response.candidates
            and response.candidates[0].content.parts
            and any(p.function_call for p in response.candidates[0].content.parts)
        ):
            # This is the full history *before* the final text answer
            history_with_tool_calls = contents + [response.candidates[0].content]

            # This recursive call will return the final text and the complete history
            final_response_content, final_history = await self._handle_function_calls(
                response,
                history_with_tool_calls,
                generate_content_config,
                vector_store_ids,
            )

            # Save the final, complete history
            if session_id:
                await gemini_session_cache.set_history(session_id, final_history)
        else:
            # No function calls, handle simple text response
            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    final_response_content = self._extract_text_from_parts(
                        candidate.content.parts
                    )

                    # Save the simple history
                    if session_id:
                        final_history = contents + [candidate.content]
                        await gemini_session_cache.set_history(
                            session_id, final_history
                        )

        # Validate structured output
        if structured_output_schema:
            try:
                import json
                import jsonschema

                parsed = json.loads(final_response_content)
                jsonschema.validate(parsed, structured_output_schema)
            except jsonschema.ValidationError as e:
                from .errors import AdapterException, ErrorCategory

                raise AdapterException(
                    f"Response does not match requested schema: {str(e)}",
                    error_category=ErrorCategory.PARSING,
                )
            except json.JSONDecodeError as e:
                from .errors import AdapterException, ErrorCategory

                raise AdapterException(
                    f"Response is not valid JSON: {str(e)}",
                    error_category=ErrorCategory.PARSING,
                )

        if return_debug:
            return {
                "content": final_response_content,
                "_debug_tools": function_declarations,
            }
        return final_response_content

    async def _handle_function_calls(
        self,
        response: Any,
        contents: List[types.Content],  # Now receives the full history so far
        config: types.GenerateContentConfig,
        vector_store_ids: Optional[List[str]] = None,
    ) -> tuple[str, list[types.Content]]:  # Return final text AND final history
        """Handle function calls in the response."""
        client = get_client()
        settings = get_settings()
        max_function_calls = settings.vertex.max_function_calls or 500
        function_call_rounds = 0

        # Process function calls iteratively
        while response.candidates and function_call_rounds < max_function_calls:
            candidate = response.candidates[0]
            if not candidate.content or not candidate.content.parts:
                break

            # Check for function calls
            function_calls = [
                part for part in candidate.content.parts if part.function_call
            ]
            if not function_calls:
                # No more function calls, extract final text
                response_text = self._extract_text_from_parts(candidate.content.parts)
                # The final history is what we built plus the final response
                final_history = contents + [candidate.content]
                return response_text, final_history

            # The model's response (function call) is already in contents from caller
            # Skip adding it again: contents.append(candidate.content)

            # Execute function calls
            function_responses = []
            for fc in function_calls:
                try:
                    if fc.function_call.name == "search_project_memory":
                        # Extract parameters
                        query = fc.function_call.args.get("query", "")
                        max_results = fc.function_call.args.get("max_results", 40)
                        store_types = fc.function_call.args.get(
                            "store_types", ["conversation", "commit"]
                        )

                        logger.info(f"Executing search_project_memory: '{query}'")

                        # Import and execute the search
                        from ...tools.search_memory import SearchMemoryAdapter

                        memory_search = SearchMemoryAdapter()
                        search_result_text = await memory_search.generate(
                            prompt=query,
                            query=query,
                            max_results=max_results,
                            store_types=store_types,
                        )

                        # Create function response
                        function_responses.append(
                            types.Part.from_function_response(
                                name=fc.function_call.name,
                                response={"result": search_result_text},
                            )
                        )

                    elif fc.function_call.name == "search_session_attachments":
                        # Extract parameters
                        query = fc.function_call.args.get("query", "")
                        max_results = fc.function_call.args.get("max_results", 20)

                        logger.info(f"Executing search_session_attachments: '{query}'")

                        # Import and execute the search
                        from ...tools.search_attachments import SearchAttachmentAdapter

                        attachment_search = SearchAttachmentAdapter()
                        search_result_text = await attachment_search.generate(
                            prompt=query,
                            query=query,
                            max_results=max_results,
                            vector_store_ids=vector_store_ids,
                        )

                        # Create function response
                        function_responses.append(
                            types.Part.from_function_response(
                                name=fc.function_call.name,
                                response={"result": search_result_text},
                            )
                        )

                except Exception as e:
                    logger.error(
                        f"Function {fc.function_call.name} failed", exc_info=True
                    )
                    # Return error to model so it can handle gracefully
                    function_responses.append(
                        types.Part.from_function_response(
                            name=fc.function_call.name,
                            response={
                                "error": f"Tool failed: {type(e).__name__}: {str(e)}"
                            },
                        )
                    )

            # Add function responses to conversation
            if function_responses:
                contents.append(types.Content(role="model", parts=function_responses))

            # Continue generation with function results
            function_call_rounds += 1
            response = await self._generate_async(
                client,
                model=self.model_name,
                contents=contents,
                config=config,
            )

        # Check if we hit the function call limit
        if function_call_rounds >= max_function_calls:
            return (
                f"TooManyFunctionCalls: Exceeded {max_function_calls} function call rounds",
                contents,
            )

        return "No response generated", contents
