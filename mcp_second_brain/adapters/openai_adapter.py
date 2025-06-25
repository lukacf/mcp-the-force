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

# Constants
POLL_INTERVAL = 3  # seconds
STREAM_TIMEOUT_THRESHOLD = (
    180  # seconds - models with longer timeouts use background mode
)
DEFAULT_TIMEOUT = 300  # seconds

# Model capabilities
SUPPORTS_STREAM: Set[str] = {
    "o3",
    "gpt-4.1",
    "o4-mini",
}  # Models that support streaming
REQUIRES_BACKGROUND: Set[str] = {"o3-pro"}  # Models that require background mode

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

        async def _execute_single_call(fc):
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
            return {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(output) if not isinstance(output, str) else output,
            }

        # Execute all function calls in parallel
        results: List[Dict[str, Any]] = await asyncio.gather(
            *[_execute_single_call(fc) for fc in function_calls]
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
        return_debug: bool = False,
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

        # Be explicit about parallel tool calls when tools are present
        if tools:
            params["parallel_tool_calls"] = True

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

        if self.model_name in REQUIRES_BACKGROUND:
            # Models like o3-pro must use background mode
            params["background"] = True
            use_background = True
        elif (
            timeout > STREAM_TIMEOUT_THRESHOLD or self.model_name not in SUPPORTS_STREAM
        ):
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
                elapsed = 0

                while elapsed < timeout:
                    job = await client.responses.retrieve(response.id)

                    if job.status == "completed":
                        # First try the convenience property
                        content = getattr(job, "output_text", "")

                        # If empty, extract text from output array (mixed content case)
                        if not content and hasattr(job, "output") and job.output:
                            text_parts = []
                            for item in job.output:
                                if (
                                    isinstance(item, dict)
                                    and item.get("type") == "message"
                                ):
                                    # Extract text from message content
                                    if "content" in item:
                                        for content_item in item["content"]:
                                            if isinstance(
                                                content_item, dict
                                            ) and content_item.get("type") in (
                                                "text",
                                                "output_text",
                                            ):
                                                text_parts.append(
                                                    content_item.get("text", "")
                                                )
                                elif hasattr(item, "type") and item.type == "message":
                                    # Handle object representation
                                    if hasattr(item, "content"):
                                        for content_item in item.content:
                                            if hasattr(
                                                content_item, "type"
                                            ) and content_item.type in (
                                                "text",
                                                "output_text",
                                            ):
                                                text_parts.append(
                                                    getattr(content_item, "text", "")
                                                )
                            if text_parts:
                                content = " ".join(text_parts)

                        # Check for function calls that need execution
                        if hasattr(job, "output") and job.output:
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
                                    "tools": tools,  # Re-attach tool schemas
                                    "parallel_tool_calls": True,  # Be explicit
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
                                remaining = timeout - elapsed
                                while elapsed_follow_up < remaining:
                                    follow_up_job = await client.responses.retrieve(
                                        follow_up.id
                                    )

                                    if follow_up_job.status == "completed":
                                        content = getattr(
                                            follow_up_job, "output_text", ""
                                        )
                                        result = {
                                            "content": content,
                                            "response_id": follow_up_job.id,
                                        }
                                        if return_debug:
                                            result["_debug_tools"] = tools
                                        return result
                                    elif follow_up_job.status not in [
                                        "queued",
                                        "in_progress",
                                    ]:
                                        raise RuntimeError(
                                            f"Follow-up job failed: {follow_up_job.status}"
                                        )

                                    await asyncio.sleep(POLL_INTERVAL)
                                    elapsed_follow_up += POLL_INTERVAL

                                    # Recalculate remaining time to prevent overrun
                                    if elapsed + elapsed_follow_up >= timeout:
                                        break

                                raise ValueError(
                                    f"Follow-up job timed out after {elapsed_follow_up}s (total: {elapsed + elapsed_follow_up}s)"
                                )

                        result = {
                            "content": content,
                            "response_id": job.id,  # type: ignore[attr-defined]
                        }
                        if return_debug:
                            result["_debug_tools"] = tools
                        return result
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

                    await asyncio.sleep(POLL_INTERVAL)
                    elapsed += POLL_INTERVAL

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
                function_calls = []
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
                        if event.type in (
                            "response.delta",
                            "ResponseOutputTextDelta",
                        ) and hasattr(event, "delta"):
                            content_parts.append(event.delta)
                        elif event.type == "response.output_text" and hasattr(
                            event, "text"
                        ):
                            content_parts.append(event.text)
                        elif (
                            event.type == "response.tool_call"
                            or event.type == "tool_call"
                        ):
                            # Collect function calls
                            function_calls.append(
                                {
                                    "type": "function_call",
                                    "name": getattr(event, "name", None),
                                    "call_id": getattr(event, "call_id", None),
                                    "arguments": getattr(event, "arguments", "{}"),
                                }
                            )
                    # Fallback for other event structures
                    elif hasattr(event, "output_text") and event.output_text:
                        content_parts.append(event.output_text)
                    elif hasattr(event, "text") and event.text:
                        content_parts.append(event.text)

                content = "".join(content_parts)

                # If we got function calls, execute them (even if text exists)
                if function_calls:
                    logger.info(
                        f"{self.model_name} streaming returned {len(function_calls)} function calls, executing them"
                    )

                    # Execute the function calls
                    results = await self._execute_function_calls(
                        function_calls, vector_store_ids
                    )

                    # Create follow-up with same tools
                    follow_up_params = {
                        "model": self.model_name,
                        "previous_response_id": response_id,
                        "input": function_calls + results,
                        "tools": tools,
                        "parallel_tool_calls": True,
                        "stream": True,  # Continue streaming
                    }

                    if temperature is not None:
                        follow_up_params["temperature"] = temperature

                    # Get follow-up response
                    follow_up_stream = await client.responses.create(**follow_up_params)

                    # Process follow-up stream
                    follow_up_content = []
                    follow_up_response_id = None
                    async for event in follow_up_stream:
                        # Capture follow-up response ID
                        if follow_up_response_id is None:
                            if (
                                hasattr(event, "id")
                                and isinstance(event.id, str)
                                and event.id.startswith("resp_")
                            ):
                                follow_up_response_id = event.id
                            elif hasattr(event, "response_id"):
                                follow_up_response_id = event.response_id

                        # Collect text content
                        if hasattr(event, "type"):
                            if event.type in (
                                "response.delta",
                                "ResponseOutputTextDelta",
                            ) and hasattr(event, "delta"):
                                follow_up_content.append(event.delta)
                        elif hasattr(event, "text") and event.text:
                            follow_up_content.append(event.text)

                    # Concatenate original content with follow-up content
                    content = content + "".join(follow_up_content)
                    # Update response_id to the follow-up if we got one
                    if follow_up_response_id:
                        response_id = follow_up_response_id

                # Log streaming summary for debugging
                logger.info(
                    f"Streaming complete for {self.model_name}: "
                    f"events={event_count}, content_length={len(content)}, "
                    f"response_id={response_id}"
                )

                result = {"content": content, "response_id": response_id}
                if return_debug:
                    result["_debug_tools"] = tools
                return result
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
