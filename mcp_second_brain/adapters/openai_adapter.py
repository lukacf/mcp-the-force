from typing import Any, Dict, List
from openai import AsyncOpenAI
from ..config import get_settings
from .base import BaseAdapter
import asyncio
import httpx

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
            # Disable read timeout to allow long-running streaming responses
            timeout=httpx.Timeout(connect=30, write=30, read=None, pool=None),
            max_retries=3,  # Enable retries for resilience
        )
    return _client


class OpenAIAdapter(BaseAdapter):
    def __init__(self, model: str):
        self.model_name = model
        self.context_window = 1_000_000 if model == "gpt-4.1" else 200_000
        self.description_snippet = (
            "Fast long-context assistant"
            if model == "gpt-4.1"
            else "Chain-of-thought helper"
        )

    async def generate(
        self,
        prompt: str,
        vector_store_ids: List[str] | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
        timeout: float = 300,
        previous_response_id: str | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
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
            **({"tools": tools} if tools else {}),
        }

        if temperature is not None:
            params["temperature"] = temperature

        if reasoning_effort:
            params["reasoning"] = {"effort": reasoning_effort}

        if previous_response_id:
            params["previous_response_id"] = previous_response_id

        # Use singleton client for connection pooling
        client = get_client()

        # Use streaming for o-series models to avoid gateway timeout
        if self.model_name.startswith("o"):
            params["stream"] = True

        try:
            if params.get("stream"):
                # Handle streaming response
                stream = await asyncio.wait_for(
                    client.responses.create(**params), timeout=timeout
                )

                # Collect all text from stream events
                content_parts = []
                response_id = None

                async for event in stream:
                    if hasattr(event, "output_text") and event.output_text:
                        content_parts.append(event.output_text)
                    elif hasattr(event, "text") and event.text:
                        content_parts.append(event.text)

                    # Capture response ID from the stream
                    if hasattr(event, "response_id"):
                        response_id = event.response_id
                    elif hasattr(stream, "response_id"):
                        response_id = stream.response_id

                return {"content": "".join(content_parts), "response_id": response_id}
            else:
                # Non-streaming response (for non-o-series models)
                response = await asyncio.wait_for(
                    client.responses.create(**params), timeout=timeout
                )
                return {
                    "content": response.output_text,  # type: ignore[attr-defined]
                    "response_id": response.id,  # type: ignore[attr-defined]
                }
        except asyncio.TimeoutError:
            raise ValueError(f"Request timed out after {timeout}s")
        except Exception as e:
            # Check for gateway timeout
            if hasattr(e, "status_code") and e.status_code == 504:
                raise ValueError(
                    "OpenAI gateway timed out. This typically happens with long-running "
                    "requests that don't use streaming. Consider using a model that "
                    "supports streaming or reducing the complexity of the request."
                )
            # Let OpenAI SDK handle retries for transient errors
            raise
