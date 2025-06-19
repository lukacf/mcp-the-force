from typing import Any, List
from google import genai
from google.genai import types
from ..config import get_settings
from .base import BaseAdapter

_set = get_settings()

# Initialize client once
_client = None

def get_client():
    global _client
    if _client is None:
        if not _set.vertex_project or not _set.vertex_location:
            raise ValueError("VERTEX_PROJECT and VERTEX_LOCATION must be configured")
        _client = genai.Client(
            vertexai=True,
            project=_set.vertex_project,
            location=_set.vertex_location,
        )
    return _client

class VertexAdapter(BaseAdapter):
    def __init__(self, model: str):
        self.model_name = model
        self.context_window = 2_000_000  # Gemini 2.5 supports up to 2M tokens
        self.description_snippet = "Deep multimodal reasoner" if "pro" in model else "Flash summary sprinter"
    
    async def generate(self, prompt: str, vector_store_ids: List[str] | None = None,
                       max_reasoning_tokens: int | None = None, temperature: float | None = None, **kwargs: Any) -> str:
        self._ensure(prompt)
        
        # Build content
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)]
            )
        ]
        
        # Configure generation
        config_params = {
            "temperature": temperature or _set.default_temperature,
            "top_p": 0.95,
            "max_output_tokens": 65535,
            "safety_settings": [
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
            ]
        }
        
        # Add thinking config for pro model with reasoning tokens
        if "pro" in self.model_name and max_reasoning_tokens:
            config_params["thinking_config"] = types.ThinkingConfig(
                thinking_budget=max_reasoning_tokens if max_reasoning_tokens > 0 else -1
            )
        
        generate_content_config = types.GenerateContentConfig(**config_params)
        
        # Note: Vector store integration would need to be handled differently for Gemini
        # Currently, Gemini doesn't have direct vector store support like OpenAI
        if vector_store_ids:
            # Log warning or implement custom retrieval logic
            pass
        
        # Generate response
        response_text = ""
        client = get_client()
        
        for chunk in client.models.generate_content_stream(
            model=self.model_name,
            contents=contents,
            config=generate_content_config,
        ):
            if chunk.text:
                response_text += chunk.text
        
        return response_text