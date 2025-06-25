from typing import Any, List
import logging
from google import genai
from google.genai import types
from ..config import get_settings
from .base import BaseAdapter
from .memory_search_declaration import create_search_memory_declaration_gemini
from .attachment_search_declaration import create_attachment_search_declaration_gemini

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
        return_debug: bool = False,
        **kwargs: Any,
    ) -> Any:
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

        # Add attachment search tool when vector stores are provided
        if vector_store_ids:
            logger.info(
                f"Registering search_session_attachments for {len(vector_store_ids)} vector stores"
            )
            attachment_search_decl = create_attachment_search_declaration_gemini()
            function_declarations.append(attachment_search_decl)

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
        if response.candidates and function_declarations:
            result = await self._handle_function_calls(
                response, contents, generate_content_config
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

        if return_debug:
            return {"content": response_text, "_debug_tools": function_declarations}
        return response_text

    async def _handle_function_calls(
        self,
        response: Any,
        contents: List[types.Content],
        config: types.GenerateContentConfig,
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
                if fc.function_call.name == "search_project_memory":
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

                elif fc.function_call.name == "search_session_attachments":
                    # Extract parameters
                    query = fc.function_call.args.get("query", "")
                    max_results = fc.function_call.args.get("max_results", 20)

                    logger.info(f"Executing search_session_attachments: '{query}'")

                    # Import and execute the search
                    from ..tools.search_attachments import SearchAttachmentAdapter

                    attachment_search = SearchAttachmentAdapter()
                    search_result_text = await attachment_search.generate(
                        prompt=query,
                        query=query,
                        max_results=max_results,
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
