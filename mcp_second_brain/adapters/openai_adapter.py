from typing import Any, Dict, List, Set
from openai import AsyncOpenAI
from ..config import get_settings
from .base import BaseAdapter
from .memory_search_declaration import create_search_memory_declaration_openai
from .attachment_search_declaration import create_attachment_search_declaration_openai
import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)

# Model capabilities
SUPPORTS_STREAM: Set[str] = {
    "o3",
    "gpt-4.1",
    "o4-mini",
}  # Models that support streaming
NO_STREAM: Set[str] = {"o3-pro"}  # Models that require background mode

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

        # Always add search_project_memory tool for accessing memory
        tools.append(create_search_memory_declaration_openai())

        # Add attachment search tool when vector stores are provided
        if vector_store_ids:
            tools.append(create_attachment_search_declaration_openai())

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

        # Choose the safest strategy based on model capabilities and timeout
        use_background = False

        if self.model_name in NO_STREAM:
            # Models like o3-pro must use background mode
            params["background"] = True
            use_background = True
        elif timeout > 180 or self.model_name not in SUPPORTS_STREAM:
            # Use background for long timeouts or unknown streaming support
            params["background"] = True
            use_background = True
        else:
            # Model supports streaming and timeout is within gateway limit
            params["stream"] = True
            use_background = False

        try:
            if use_background:
                # Handle background mode (for o3-pro)
                response = await client.responses.create(**params)

                # Poll for completion
                poll_interval = 3  # seconds (reduced from 5 for better responsiveness)
                elapsed = 0

                while elapsed < timeout:
                    job = await client.responses.retrieve(response.id)

                    if job.status == "completed":
                        return {
                            "content": job.output_text,  # type: ignore[attr-defined]
                            "response_id": job.id,  # type: ignore[attr-defined]
                        }
                    elif job.status not in ["queued", "in_progress"]:
                        # Handle failed, cancelled, or unknown status
                        error_msg = getattr(job, "error", {})
                        if isinstance(error_msg, dict):
                            error_detail = error_msg.get("message", "Unknown error")
                        else:
                            error_detail = (
                                str(error_msg) if error_msg else "Unknown error"
                            )
                        raise RuntimeError(
                            f"Job failed with status={job.status}: {error_detail}"
                        )

                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval

                # Timeout reached
                raise ValueError(
                    f"Job {response.id} still not finished after {timeout}s "
                    f"(status: {job.status})"
                )
            else:
                # Streaming response (for models that support it)
                stream = await asyncio.wait_for(
                    client.responses.create(**params), timeout=timeout
                )

                # Capture response ID from the stream object itself (not from events)
                # This is critical for conversation continuity
                response_id = getattr(stream, "response_id", None)
                logger.info(f"Captured response_id from stream: {response_id}")

                # Collect all text from stream events
                content_parts = []

                async for event in stream:
                    if hasattr(event, "output_text") and event.output_text:
                        content_parts.append(event.output_text)
                    elif hasattr(event, "text") and event.text:
                        content_parts.append(event.text)

                return {"content": "".join(content_parts), "response_id": response_id}
        except asyncio.TimeoutError:
            raise ValueError(f"Request timed out after {timeout}s")
        except Exception as e:
            # Check for gateway timeout
            if hasattr(e, "status_code") and e.status_code in [504, 524]:
                raise ValueError(
                    f"Gateway timeout ({e.status_code}) after ~100-180s of idle time. "
                    f"Model: {self.model_name}. This happens when non-streaming requests "
                    f"take too long to produce output. The request may still be processing "
                    f"server-side. For {self.model_name}, background mode should have been "
                    f"used automatically - this error suggests a configuration issue."
                )
            # Let OpenAI SDK handle retries for transient errors
            raise
