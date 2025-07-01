from typing import Any, List, Optional, Dict
import asyncio
import logging
import threading
import json
from google import genai
from google.genai import types
from google.genai.types import HarmCategory, HarmBlockThreshold
from ...config import get_settings
from ..base import BaseAdapter
from ..memory_search_declaration import create_search_memory_declaration_gemini
from ..attachment_search_declaration import create_attachment_search_declaration_gemini
from ...utils.validation import validate_json_schema
from jsonschema import ValidationError

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
        self.context_window = 2_000_000  # Gemini 2.5 supports up to 2M tokens
        self.description_snippet = (
            "Deep multimodal reasoner" if "pro" in model else "Flash summary sprinter"
        )

    async def _generate_async(self, client, **kwargs):
        """Async wrapper for synchronous generate_content calls."""
        try:
            return await asyncio.to_thread(client.models.generate_content, **kwargs)
        except asyncio.CancelledError:
            raise

    async def generate(
        self,
        prompt: str,
        vector_store_ids: List[str] | None = None,
        max_reasoning_tokens: int | None = None,
        temperature: float | None = None,
        return_debug: bool = False,
        messages: Optional[List[Dict[str, str]]] = None,
        system_instruction: Optional[str] = None,
        structured_output_schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        self._ensure(prompt)

        if messages:
            contents = [
                types.Content(
                    role=m.get("role", "user"),
                    parts=[types.Part.from_text(text=m.get("content", ""))],
                )
                for m in messages
            ]
        else:
            contents = [
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

        # Add thinking config for pro models
        if "pro" in self.model_name and max_reasoning_tokens:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=max_reasoning_tokens if max_reasoning_tokens > 0 else -1
            )

        generate_content_config = types.GenerateContentConfig(**config_kwargs)

        # Generate response
        client = get_client()
        response = await self._generate_async(
            client,
            model=self.model_name,
            contents=contents,
            config=generate_content_config,
        )

        # Handle function calls if any
        if response.candidates and function_declarations:
            result = await self._handle_function_calls(
                response, contents, generate_content_config, vector_store_ids
            )
            if return_debug:
                return {"content": result, "_debug_tools": function_declarations}
            return result

        # Extract text from response
        response_text = ""
        if response.candidates:
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.text:
                            response_text += part.text

        # Validate structured output if schema was provided
        if structured_output_schema:
            try:
                parsed_json = json.loads(response_text)
                validate_json_schema(parsed_json, structured_output_schema)
                logger.info("Structured output validated successfully.")
            except json.JSONDecodeError as e:
                logger.error(f"Structured output JSON parse failed: {e}")
                raise Exception(
                    f"Structured output validation failed: Invalid JSON. Error: {e}"
                )
            except ValidationError as e:
                logger.error(f"Structured output schema validation failed: {e}")
                raise Exception(f"Structured output validation failed: {e.message}")

        if return_debug:
            return {"content": response_text, "_debug_tools": function_declarations}
        return response_text

    async def _handle_function_calls(
        self,
        response: Any,
        contents: List[types.Content],
        config: types.GenerateContentConfig,
        vector_store_ids: Optional[List[str]] = None,
    ) -> str:
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
                response_text = ""
                for part in candidate.content.parts:
                    if part.text:
                        response_text += part.text
                return response_text

            # Add model's response to conversation
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
            return f"TooManyFunctionCalls: Exceeded {max_function_calls} function call rounds"

        return "No response generated"
