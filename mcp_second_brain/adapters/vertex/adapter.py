from typing import Any, List, Optional, Dict
import asyncio
import logging
import time
from google import genai
from google.genai import types
from google.genai.types import HarmCategory, HarmBlockThreshold
import google.api_core.exceptions
from ...config import get_settings
from ..base import BaseAdapter
from ..memory_search_declaration import create_search_memory_declaration_gemini
from ..task_files_search_declaration import create_task_files_search_declaration_gemini
from ...gemini_session_cache import gemini_session_cache
from .errors import AdapterException, ErrorCategory

# Removed validation imports - no longer validating structured output
# from ...utils.validation import validate_json_schema
# from jsonschema import ValidationError
from .models import model_capabilities

logger = logging.getLogger(__name__)

# Singleton client instance - safe for async use
_client: Optional[genai.Client] = None


def get_client():
    """Get the shared Vertex AI client instance."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.vertex_project or not settings.vertex_location:
            raise ValueError("VERTEX_PROJECT and VERTEX_LOCATION must be configured")
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
        """Use native async API for generate_content calls."""
        try:
            logger.info(
                f"[ADAPTER] Starting Vertex async generate_content at {time.strftime('%H:%M:%S')}"
            )
            api_start_time = time.time()
            # Use the async client API directly
            result = await client.aio.models.generate_content(**kwargs)
            api_end_time = time.time()
            logger.info(
                f"[ADAPTER] Vertex async generate_content completed in {api_end_time - api_start_time:.2f}s"
            )
            return result
        except asyncio.CancelledError:
            logger.warning("[CANCEL] Vertex generate_content cancelled")
            logger.info(
                f"[CANCEL] Active tasks in Vertex cancel: {len(asyncio.all_tasks())}"
            )
            logger.info("[CANCEL] Re-raising from Vertex adapter")
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

        # Setup tools
        function_declarations = []

        # Add search_project_memory unless explicitly disabled
        disable_memory_search = kwargs.pop("disable_memory_search", False)
        if not disable_memory_search:
            memory_search_decl = create_search_memory_declaration_gemini()
            function_declarations.append(
                types.FunctionDeclaration(**memory_search_decl)
            )

        # Add attachment search tool when vector stores are provided
        if vector_store_ids:
            logger.info(
                f"Registering search_task_files for {len(vector_store_ids)} vector stores"
            )
            task_files_search_decl = create_task_files_search_declaration_gemini()
            function_declarations.append(
                types.FunctionDeclaration(**task_files_search_decl)
            )

        # Build tools list
        tools: Optional[List[Any]] = None
        if function_declarations:
            tools = [types.Tool(function_declarations=function_declarations)]

        # Build config with explicit parameters
        settings = get_settings()
        max_tokens = settings.vertex.max_output_tokens or 65535

        # Build base config
        actual_temperature = (
            temperature if temperature is not None else settings.default_temperature
        )
        logger.info(
            f"Using temperature: {actual_temperature} (requested: {temperature}, default: {settings.default_temperature})"
        )

        config_kwargs = {
            "temperature": actual_temperature,
            "top_p": 0.95,
            "max_output_tokens": max_tokens,
            "safety_settings": safety_settings,
            "tools": tools,
        }

        # Add response_schema for structured output
        # NOTE: Gemini's structured output only supports a subset of JSON Schema:
        # - Basic types: string, integer, number, boolean, array, object
        # - Constraints: enum, required, minItems, maxItems, properties
        # - NOT supported: pattern (regex), minLength, maxLength, additionalProperties
        # See: https://ai.google.dev/gemini-api/docs/structured-output
        if structured_output_schema:
            logger.debug(f"Setting response_schema: {structured_output_schema}")
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

        # Convert response_schema to types.Schema if it's a dict
        response_schema = config_kwargs.get("response_schema")
        if response_schema and isinstance(response_schema, dict):
            # Recursively convert dict schema to types.Schema objects
            def dict_to_schema(d: Dict[str, Any]) -> types.Schema:
                """Convert a dict representation to google.genai.types.Schema."""
                schema_kwargs = {}

                # Map the type to proper enum
                if "type" in d:
                    type_str = d["type"]
                    # Map string types to google.genai.types.Type enum
                    # Handle both lowercase (standard JSON Schema) and uppercase (pre-converted)
                    type_map = {
                        "object": types.Type.OBJECT,
                        "array": types.Type.ARRAY,
                        "string": types.Type.STRING,
                        "integer": types.Type.INTEGER,
                        "number": types.Type.NUMBER,
                        "boolean": types.Type.BOOLEAN,
                        "null": types.Type.NULL,
                        # Also support uppercase for backwards compatibility
                        "OBJECT": types.Type.OBJECT,
                        "ARRAY": types.Type.ARRAY,
                        "STRING": types.Type.STRING,
                        "INTEGER": types.Type.INTEGER,
                        "NUMBER": types.Type.NUMBER,
                        "BOOLEAN": types.Type.BOOLEAN,
                        "NULL": types.Type.NULL,
                    }
                    schema_kwargs["type"] = type_map.get(type_str, types.Type.STRING)

                # Handle properties for OBJECT type
                if "properties" in d and isinstance(d["properties"], dict):
                    schema_kwargs["properties"] = {
                        key: dict_to_schema(value) if isinstance(value, dict) else value
                        for key, value in d["properties"].items()
                    }

                # Handle array items
                if "items" in d and isinstance(d["items"], dict):
                    schema_kwargs["items"] = dict_to_schema(d["items"])

                # Copy all other fields that aren't already handled
                # This ensures we don't lose any JSON Schema properties
                handled_fields = {"type", "properties", "items"}
                for field, value in d.items():
                    if field not in handled_fields:
                        schema_kwargs[field] = value

                return types.Schema(**schema_kwargs)

            response_schema = dict_to_schema(response_schema)
            config_kwargs["response_schema"] = response_schema

        # Create GenerateContentConfig with explicit parameters
        final_temperature = config_kwargs.get("temperature")
        logger.info(f"Final temperature for GenerateContentConfig: {final_temperature}")

        generate_content_config = types.GenerateContentConfig(
            temperature=final_temperature,
            top_p=config_kwargs.get("top_p"),
            max_output_tokens=config_kwargs.get("max_output_tokens"),
            safety_settings=config_kwargs.get("safety_settings"),
            tools=config_kwargs.get("tools"),
            response_schema=response_schema,
            response_mime_type=config_kwargs.get("response_mime_type"),
            system_instruction=config_kwargs.get("system_instruction"),
            thinking_config=config_kwargs.get("thinking_config"),
        )

        # Generate response
        try:
            client = get_client()
        except ValueError as e:
            # Handle configuration errors
            logger.error(f"Failed to initialize Vertex client: {e}")
            raise AdapterException(
                f"Vertex AI configuration error: {str(e)}",
                error_category=ErrorCategory.CONFIGURATION,
                original_error=e,
            )
        except Exception as e:
            # Handle other initialization errors
            logger.error(
                f"Unexpected error initializing Vertex client: {e}", exc_info=True
            )
            raise AdapterException(
                f"Failed to initialize Vertex AI client: {str(e)}",
                error_category=ErrorCategory.INITIALIZATION,
                original_error=e,
            )

        try:
            response = await self._generate_async(
                client,
                model=self.model_name,
                contents=contents,
                config=generate_content_config,
            )
        except Exception as e:
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
                # Use the SDK's built-in text extraction which handles JSON mode properly
                # But handle the case where response might be a mock object in tests
                try:
                    final_response_content = response.text or ""
                except AttributeError:
                    # Fallback for tests or when response doesn't have .text
                    if candidate.content and candidate.content.parts:
                        final_response_content = self._extract_text_from_parts(
                            candidate.content.parts
                        )
                    else:
                        final_response_content = ""

                # Save the simple history
                if session_id:
                    final_history = contents + [candidate.content]
                    await gemini_session_cache.set_history(session_id, final_history)

        # Extract clean JSON if structured output was requested
        # NOTE: We rely on Gemini to enforce the schema via response_schema parameter.
        # We do NOT validate the response ourselves because:
        # 1. Gemini should enforce the schema during generation
        # 2. Validation would fail with converted schemas (uppercase types)
        # 3. Some constraints (like pattern) are not enforced by Gemini anyway
        if structured_output_schema:
            try:
                from ...utils.json_extractor import extract_json

                # Extract JSON from potential markdown wrapping
                final_response_content = extract_json(final_response_content)
            except ValueError as e:
                # If we can't extract JSON, log but continue
                # Return the raw response - let the caller handle it
                logger.warning(f"Could not extract JSON from structured response: {e}")
                pass

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

            # For the first iteration, the model's response is already in contents from caller
            # For subsequent iterations, we need to add it
            if function_call_rounds > 0:
                contents.append(candidate.content)

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

                    elif fc.function_call.name == "search_task_files":
                        # Extract parameters
                        query = fc.function_call.args.get("query", "")
                        max_results = fc.function_call.args.get("max_results", 20)

                        logger.info(f"Executing search_task_files: '{query}'")

                        # Import and execute the search
                        from ...tools.search_task_files import SearchTaskFilesAdapter

                        task_files_search = SearchTaskFilesAdapter()
                        search_result_text = await task_files_search.generate(
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
            # Function responses must be added as user messages in Gemini
            if function_responses:
                contents.append(types.Content(role="user", parts=function_responses))

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
