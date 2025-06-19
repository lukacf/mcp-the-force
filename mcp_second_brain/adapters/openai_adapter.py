from typing import Any, Dict, List
from openai import OpenAI
from ..config import get_settings
from .base import BaseAdapter

# Initialize client lazily to avoid errors on startup
_client = None

def get_client():
    global _client
    if _client is None:
        api_key = get_settings().openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        _client = OpenAI(api_key=api_key)
    return _client

class OpenAIAdapter(BaseAdapter):
    def __init__(self, model: str):
        self.model_name = model
        self.context_window = 1_000_000 if model == "gpt-4.1" else 200_000
        self.description_snippet = "Fast long-context assistant" if model == "gpt-4.1" else "Chain-of-thought helper"
    
    def generate(self, prompt: str, vector_store_ids: List[str] | None = None,
                 temperature: float | None = None, reasoning_effort: str | None = None, **kwargs: Any) -> str:
        self._ensure(prompt)
        
        msgs = [{"role": "user", "content": prompt}]
        tools = [{"type": "file_search", "vector_store_ids": vector_store_ids}] if vector_store_ids else []
        
        params: Dict[str, Any] = {
            "model": self.model_name,
            "input": msgs,
            **({"tools": tools} if tools else {})
        }
        
        if temperature is not None:
            params["temperature"] = temperature
        
        if reasoning_effort:
            params["reasoning"] = {"effort": reasoning_effort}
        
        return get_client().responses.create(**params).output_text  # type: ignore[attr-defined]