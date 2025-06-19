from abc import ABC, abstractmethod
from typing import Any, List
from ..utils.token_counter import count_tokens

class BaseAdapter(ABC):
    model_name: str
    context_window: int
    description_snippet: str
    
    def _ensure(self, prompt: str, buf: int = 10000):
        if count_tokens([prompt]) + buf > self.context_window:
            raise ValueError("Prompt too large")
    
    @abstractmethod
    def generate(self, prompt: str, vector_store_ids: List[str] | None = None, **kw: Any) -> str:
        ...