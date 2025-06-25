from typing import Any, Dict, List, Set
from openai import AsyncOpenAI
from ..config import get_settings
from .base import BaseAdapter
from .memory_search_declaration import create_search_memory_declaration_openai
from .attachment_search_declaration import create_attachment_search_declaration_openai
import asyncio
import httpx
import logging
import json

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

    async def _execute_function_calls(
        self, function_calls: List[Any], vector_store_ids: List[str] | None = None
    ) -> List[Dict[str, Any]]:
        """Execute function calls and return results."""
        results = []

        for fc in function_calls:
            # Extract function details
            name = fc.get("name") if isinstance(fc, dict) else getattr(fc, "name", None)
            call_id = (
                fc.get("call_id")
                if isinstance(fc, dict)
                else getattr(fc, "call_id", None)
            )
            arguments = (
                fc.get("arguments")
                if isinstance(fc, dict)
                else getattr(fc, "arguments", "{}")
            )

            try:
                args = (
                    json.loads(arguments) if isinstance(arguments, str) else arguments
                )
            except json.JSONDecodeError:
                args = {}

            # Execute the function based on its name
            output = None
            if name == "search_project_memory":
                # Import and execute search
                from ..tools.search_memory import SearchMemoryAdapter

                adapter = SearchMemoryAdapter()
                output = await adapter.generate(
                    prompt=args.get("query", ""),
                    query=args.get("query", ""),
                    max_results=args.get("max_results", 40),
                    store_types=args.get("store_types", ["conversation", "commit"]),
                )
            elif name == "search_session_attachments":
                # Import and execute attachment search
                from ..tools.search_attachments import SearchAttachmentAdapter

                attachment_adapter = SearchAttachmentAdapter()
                output = await attachment_adapter.generate(
                    prompt=args.get("query", ""),
                    query=args.get("query", ""),
                    max_results=args.get("max_results", 20),
                    vector_store_ids=vector_store_ids,
                )
            else:
                output = f"Unknown function: {name}"

            # Format the result
            results.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(output)
                    if not isinstance(output, str)
                    else output,
                }
            )

        return results

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
                        # Check if response contains function calls
                        content = getattr(job, "output_text", "")

                        if hasattr(job, "output") and job.output and not content:
                            function_calls = [
                                item
                                for item in job.output
                                if (
                                    hasattr(item, "type")
                                    and item.type == "function_call"
                                )
                                or (
                                    isinstance(item, dict)
                                    and item.get("type") == "function_call"
                                )
                            ]

                            if function_calls:
                                logger.info(
                                    f"{self.model_name} returned {len(function_calls)} function calls, executing them"
                                )

                                # Execute the function calls
                                results = await self._execute_function_calls(
                                    function_calls, vector_store_ids
                                )

                                # Send results back to the model
                                follow_up_params = {
                                    "model": self.model_name,
                                    "previous_response_id": job.id,
                                    "input": function_calls
                                    + results,  # Include both calls and results
                                }

                                # Add reasoning parameters if present
                                if reasoning_effort:
                                    follow_up_params["reasoning"] = {
                                        "effort": reasoning_effort
                                    }

                                # Get the final response
                                follow_up = await client.responses.create(
                                    **follow_up_params
                                )

                                # Wait for follow-up completion
                                elapsed_follow_up = 0
                                while elapsed_follow_up < timeout - elapsed:
                                    follow_up_job = await client.responses.retrieve(
                                        follow_up.id
                                    )

                                    if follow_up_job.status == "completed":
                                        content = getattr(
                                            follow_up_job, "output_text", ""
                                        )
                                        return {
                                            "content": content,
                                            "response_id": follow_up_job.id,
                                        }
                                    elif follow_up_job.status not in [
                                        "queued",
                                        "in_progress",
                                    ]:
                                        raise RuntimeError(
                                            f"Follow-up job failed: {follow_up_job.status}"
                                        )

                                    await asyncio.sleep(poll_interval)
                                    elapsed_follow_up += poll_interval

                                raise ValueError("Follow-up job timed out")

                        return {
                            "content": content,
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

                response_id = None
                content_parts = []
                event_count = 0

                async for event in stream:
                    event_count += 1
                    # Capture the response ID as soon as it's available in an event.
                    # It should be the same across all events for a given response.
                    if response_id is None:
                        # The main response object has an 'id' field starting with 'resp_'.
                        # This is the most reliable attribute based on OpenAI's API structure.
                        if (
                            hasattr(event, "id")
                            and isinstance(event.id, str)
                            and event.id.startswith("resp_")
                        ):
                            response_id = event.id
                            logger.info(
                                f"Captured response ID from event 'id' attribute: {response_id}"
                            )
                        # Fallback for other possible attribute names like 'response_id'
                        elif hasattr(event, "response_id"):
                            response_id = event.response_id
                            logger.info(
                                f"Captured response ID from event 'response_id' attribute: {response_id}"
                            )

                    # Handle streaming events based on event type
                    if hasattr(event, "type"):
                        if event.type == "ResponseOutputTextDelta" and hasattr(
                            event, "delta"
                        ):
                            content_parts.append(event.delta)
                        elif event.type == "response.output_text" and hasattr(
                            event, "text"
                        ):
                            content_parts.append(event.text)
                    # Fallback for other event structures
                    elif hasattr(event, "output_text") and event.output_text:
                        content_parts.append(event.output_text)
                    elif hasattr(event, "text") and event.text:
                        content_parts.append(event.text)

                content = "".join(content_parts)

                # Log streaming summary for debugging
                logger.info(
                    f"Streaming complete for {self.model_name}: "
                    f"events={event_count}, content_length={len(content)}, "
                    f"response_id={response_id}"
                )

                # O3 models may take time to start streaming content
                # If we got a response_id but no content, it likely means the model
                # is still processing. This shouldn't happen with proper streaming.
                if not content and response_id:
                    logger.warning(
                        f"Received response_id {response_id} but no content for {self.model_name}. "
                        f"Events received: {event_count}. The model may still be processing."
                    )
                    # Return a more informative message rather than empty content
                    content = f"Model {self.model_name} acknowledged request (response_id: {response_id}) but did not produce output within the streaming window."

                return {"content": content, "response_id": response_id}
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
