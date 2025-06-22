from typing import Any, Dict, List
from openai import AsyncOpenAI
from ..config import get_settings
from .base import BaseAdapter
import asyncio

# Initialize client lazily to avoid errors on startup
_client = None

def get_client():
    global _client
    if _client is None:
        api_key = get_settings().openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        _client = AsyncOpenAI(
            api_key=api_key,
            timeout=30.0,
            max_retries=3  # Enable retries for resilience
        )
    return _client

class OpenAIAdapter(BaseAdapter):
    def __init__(self, model: str):
        self.model_name = model
        self.context_window = 1_000_000 if model == "gpt-4.1" else 200_000
        self.description_snippet = "Fast long-context assistant" if model == "gpt-4.1" else "Chain-of-thought helper"
    
    async def generate(self, prompt: str, vector_store_ids: List[str] | None = None,
                       temperature: float | None = None, reasoning_effort: str | None = None, 
                       timeout: float = 300, previous_response_id: str | None = None,
                       **kwargs: Any) -> Dict[str, Any]:
        self._ensure(prompt)
        
        msgs = [{"role": "user", "content": prompt}]
        tools = []
        
        # Add file search if vector stores provided
        if vector_store_ids:
            tools.append({"type": "file_search", "vector_store_ids": vector_store_ids})
        
        # Add web search for GPT-4.1
        if self.model_name == "gpt-4.1":
            tools.append({"type": "web_search"})
        
        params: Dict[str, Any] = {
            "model": self.model_name,
            "input": msgs,
            **({"tools": tools} if tools else {})
        }
        
        if temperature is not None:
            params["temperature"] = temperature
        
        if reasoning_effort:
            params["reasoning"] = {"effort": reasoning_effort}
        
        if previous_response_id:
            params["previous_response_id"] = previous_response_id
        
        # Use singleton client for connection pooling
        client = get_client()
        
        try:
            response = await asyncio.wait_for(
                client.responses.create(**params),
                timeout=timeout
            )
            return {
                "content": response.output_text,  # type: ignore[attr-defined]
                "response_id": response.id  # type: ignore[attr-defined]
            }
        except asyncio.TimeoutError:
            raise ValueError(f"Request timed out after {timeout}s")
        except Exception:
            # Let OpenAI SDK handle retries for transient errors
            raise