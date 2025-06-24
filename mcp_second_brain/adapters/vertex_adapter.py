from typing import Any, List
import logging
from google import genai
from google.genai import types
from ..config import get_settings
from .base import BaseAdapter
from .vertex_file_search import GeminiFileSearch, create_file_search_declaration
from .memory_search_declaration import create_search_memory_declaration_gemini

logger = logging.getLogger(__name__)

# Initialize client once
_client = None


def get_client():
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
        self.context_window = 2_000_000  # Gemini 2.5 supports up to 2M tokens
        self.description_snippet = (
            "Deep multimodal reasoner" if "pro" in model else "Flash summary sprinter"
        )

    async def generate(
        self,
        prompt: str,
        vector_store_ids: List[str] | None = None,
        max_reasoning_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> str:
        self._ensure(prompt)

        # Build initial content
        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        ]

        # Configure generation
        config_params = {
            "temperature": temperature or get_settings().default_temperature,
            "top_p": 0.95,
            "max_output_tokens": 65535,
            "safety_settings": [
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT", threshold="OFF"
                ),
            ],
        }

        # Add thinking config for pro model with reasoning tokens
        if "pro" in self.model_name and max_reasoning_tokens:
            config_params["thinking_config"] = types.ThinkingConfig(
                thinking_budget=max_reasoning_tokens if max_reasoning_tokens > 0 else -1
            )

        # Setup tools - always include search_project_memory
        function_declarations = []

        # Always add search_project_memory for accessing memory
        memory_search_decl = create_search_memory_declaration_gemini()
        function_declarations.append(memory_search_decl)

        # Setup file_search function if vector stores provided (for user attachments)
        file_search = None
        if vector_store_ids:
            logger.info(
                f"Registering file_search for {len(vector_store_ids)} vector stores"
            )
            file_search = GeminiFileSearch(vector_store_ids)

            # Create function declaration for Gemini
            file_search_decl = create_file_search_declaration()
            function_declarations.append(file_search_decl)

        # Add tools to config if we have any functions
        if function_declarations:
            tools = [types.Tool(function_declarations=function_declarations)]
            config_params["tools"] = tools

        generate_content_config = types.GenerateContentConfig(**config_params)

        # Generate response
        client = get_client()
        response = client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=generate_content_config,
        )

        # Handle function calls if any
        if file_search and response.candidates:
            return await self._handle_function_calls(
                response, contents, generate_content_config, file_search
            )

        # Extract text from response
        response_text = ""
        if response.candidates:
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.text:
                            response_text += part.text

        return response_text

    async def _handle_function_calls(
        self,
        response: Any,
        contents: List[types.Content],
        config: types.GenerateContentConfig,
        file_search: GeminiFileSearch,
    ) -> str:
        """Handle function calls in the response."""
        client = get_client()

        # Process function calls iteratively
        while response.candidates:
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
                if fc.function_call.name == "file_search_msearch":
                    # Extract queries parameter
                    queries = fc.function_call.args.get("queries", [])
                    logger.info(f"Executing file_search with {len(queries)} queries")

                    # Execute search
                    search_results = await file_search.msearch(queries)

                    # Create function response
                    function_responses.append(
                        types.Part.from_function_response(
                            name=fc.function_call.name, response=search_results
                        )
                    )

                elif fc.function_call.name == "search_project_memory":
                    # Extract parameters
                    query = fc.function_call.args.get("query", "")
                    max_results = fc.function_call.args.get("max_results", 40)
                    store_types = fc.function_call.args.get(
                        "store_types", ["conversation", "commit"]
                    )

                    logger.info(f"Executing search_project_memory: '{query}'")

                    # Import and execute the search
                    from ..tools.search_memory import SearchMemoryAdapter

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

            # Add function responses to conversation
            if function_responses:
                contents.append(types.Content(role="model", parts=function_responses))

            # Continue generation with function results
            response = client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

        return "No response generated"
