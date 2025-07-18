from abc import ABC, abstractmethod
from typing import Any, List, Dict, Union
from ..utils.token_counter import count_tokens


class BaseAdapter(ABC):
    """Base adapter for AI models.
    
    ⚠️  CRITICAL REQUIREMENT FOR NEW ADAPTERS ⚠️
    
    Due to an unpatched bug in the Python MCP library, ALL adapters MUST implement
    cancellation handling to prevent server crashes and double responses.
    
    Required steps for new adapters:
    1. Create a cancel_aware_flow.py in your adapter's directory
    2. Import it in your adapter's __init__.py: 
       from . import cancel_aware_flow  # noqa: F401
    3. Implement a cancellation test in tests/unit/adapters/
    
    See existing adapters (openai, grok, vertex) for examples.
    
    This workaround is scheduled for removal when:
    - MCP library fixes the cancellation bug, OR
    - Q3 2025 (whichever comes first)
    
    Tracking PR: https://github.com/modelcontextprotocol/python-sdk/pull/1153
    """
    model_name: str
    context_window: int
    description_snippet: str

    def _ensure(self, prompt: str, buf: int = 10000):
        if count_tokens([prompt]) + buf > self.context_window:
            raise ValueError("Prompt too large")

    @abstractmethod
    async def generate(
        self, prompt: str, vector_store_ids: List[str] | None = None, **kw: Any
    ) -> Union[str, Dict[str, Any]]: ...
