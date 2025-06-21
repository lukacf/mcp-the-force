"""Mock adapter for integration testing."""
import json
from .base import BaseAdapter


class MockAdapter(BaseAdapter):
    """Lightweight mock that echoes metadata for routing validation."""
    
    description_snippet = "Mock adapter for testing"
    context_window = 1_000_000
    
    def __init__(self, model_name: str):
        """Initialize with model name."""
        self.model_name = model_name
    
    async def generate(self, prompt: str, vector_store_ids=None, **kwargs):
        """Return JSON metadata about the call."""
        return json.dumps({
            "mock": True,
            "model": self.model_name,
            "prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt,
            "prompt_length": len(prompt),
            "vector_store_ids": vector_store_ids,
            "adapter_kwargs": kwargs,
        }, indent=2)