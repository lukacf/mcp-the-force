"""Flow orchestration for OpenAI adapter using Strategy Pattern."""

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Set
from dataclasses import dataclass

from .client import OpenAIClientFactory
from .models import OpenAIRequest, model_capabilities
from .tool_exec import ToolExecutor, BuiltInToolDispatcher
from .errors import (
    AdapterException,
    ErrorCategory,
    TimeoutException,
    GatewayTimeoutException,
)
from .constants import (
    INITIAL_POLL_DELAY_SEC,
    MAX_POLL_INTERVAL_SEC,
    STREAM_TIMEOUT_THRESHOLD,
)
from ..memory_search_declaration import create_search_memory_declaration_openai
from ..attachment_search_declaration import create_attachment_search_declaration_openai
import json
import jsonschema

logger = logging.getLogger(__name__)


@dataclass
class FlowContext:
    """Context passed between flow stages."""

    request: OpenAIRequest
    client: Any  # AsyncOpenAI
    tools: List[Dict[str, Any]]
    tool_executor: ToolExecutor
    start_time: float
    timeout_remaining: float

    def update_timeout(self, elapsed: float):
        """Update remaining timeout after elapsed time."""
        self.timeout_remaining = max(0, self.timeout_remaining - elapsed)


class BaseFlowStrategy(ABC):
    """Base strategy for flow execution."""

    def __init__(self, context: FlowContext):
        self.context = context
        self.telemetry: Dict[str, Any] = {}  # For debugging/metrics

    @abstractmethod
    async def execute(self) -> Dict[str, Any]:
        """Execute the flow and return the result."""
        pass

    def _build_tools_list(self) -> List[Dict[str, Any]]:
        """Build the tools list based on request and model capabilities."""
        import logging

        logger = logging.getLogger(__name__)

        tools = []

        capability = model_capabilities.get(self.context.request.model)

        # Only add custom tools if the model supports them
        if capability is None or capability.supports_custom_tools:
            # Add search_project_memory tool unless disabled
            if not self.context.request.disable_memory_search:
                tools.append(create_search_memory_declaration_openai())

            # Add attachment search if vector stores provided
            logger.info(
                f"{self.context.request.model}: vector_store_ids={self.context.request.vector_store_ids}"
            )
            if self.context.request.vector_store_ids:
                tools.append(create_attachment_search_declaration_openai())

        # Add web search for supported models
        if capability and capability.supports_web_search:
            tools.append({"type": capability.web_search_tool})

        # Add any custom tools from request (only if allowed)
        if capability is None or capability.supports_custom_tools:
            if self.context.request.tools:
                tools.extend(self.context.request.tools)

        return tools

    def _extract_content_from_output(self, response: Any) -> str:
        """Extract text content from various response formats."""
        # First try the convenience property
        content = getattr(response, "output_text", "")

        # If empty, extract from output array
        if not content and hasattr(response, "output") and response.output:
            text_parts = []

            for item in response.output:
                if isinstance(item, dict):
                    # Handle dict representation
                    if item.get("type") == "message" and "content" in item:
                        for content_item in item["content"]:
                            if isinstance(content_item, dict) and content_item.get(
                                "type"
                            ) in ("text", "output_text"):
                                text_parts.append(content_item.get("text", ""))
                else:
                    # Handle object representation
                    if (
                        hasattr(item, "type")
                        and item.type == "message"
                        and hasattr(item, "content")
                    ):
                        for content_item in item.content:
                            if hasattr(content_item, "type") and content_item.type in (
                                "text",
                                "output_text",
                            ):
                                text_parts.append(getattr(content_item, "text", ""))
                            elif isinstance(content_item, dict) and content_item.get(
                                "type"
                            ) in ("text", "output_text"):
                                text_parts.append(content_item.get("text", ""))

            if text_parts:
                content = "".join(text_parts)

        return content

    def _extract_function_calls(self, response: Any) -> List[Any]:
        """Extract and deduplicate function calls from response."""
        if not hasattr(response, "output") or not response.output:
            return []

        seen_call_ids = set()
        function_calls = []

        for item in response.output:
            # Handle both dict and object representations
            if isinstance(item, dict):
                if item.get("type") == "function_call":
                    call_id = item.get("call_id")
                    if call_id and call_id not in seen_call_ids:
                        seen_call_ids.add(call_id)
                        function_calls.append(item)
            else:
                if hasattr(item, "type") and item.type == "function_call":
                    call_id = getattr(item, "call_id", None)
                    if call_id and call_id not in seen_call_ids:
                        seen_call_ids.add(call_id)
                        function_calls.append(item)

        return function_calls

    def _collect_all_output_items(self, response: Any) -> List[Any]:
        """Collect all output items including reasoning for preservation."""
        if not hasattr(response, "output") or not response.output:
            return []
        return list(response.output)

    def _validate_structured_output(self, content: str) -> None:
        """Validate structured output against schema."""
        if not self.context.request.structured_output_schema:
            return

        try:
            parsed = json.loads(content)
            jsonschema.validate(parsed, self.context.request.structured_output_schema)
        except jsonschema.ValidationError as e:
            raise AdapterException(
                ErrorCategory.PARSING,
                f"Response does not match requested schema: {str(e)}",
            )
        except json.JSONDecodeError as e:
            raise AdapterException(
                ErrorCategory.PARSING, f"Response is not valid JSON: {str(e)}"
            )

    async def _handle_function_calls(
        self,
        function_calls: List[Any],
        original_response_id: str,
        all_output_items: List[Any],
    ) -> Dict[str, Any]:
        """Execute function calls and get follow-up response."""
        logger.info(
            f"{self.context.request.model} returned {len(function_calls)} function calls"
        )

        # Execute the function calls with bounded concurrency
        results = await self.context.tool_executor.run_all(function_calls)

        # When using previous_response_id, we only send the function call results
        # The API manages the conversation state server-side
        follow_up_input = results

        # Build follow-up parameters
        follow_up_params: Dict[str, Any] = {
            "model": self.context.request.model,
            "previous_response_id": original_response_id,
            "messages": follow_up_input,  # Use messages for OpenAIRequest validation
            "tools": self.context.tools,
            "parallel_tool_calls": self.context.request.parallel_tool_calls,
        }

        # Add optional parameters
        if self.context.request.temperature is not None:
            follow_up_params["temperature"] = self.context.request.temperature

        if self.context.request.reasoning_effort:
            follow_up_params["reasoning_effort"] = self.context.request.reasoning_effort

        # Preserve vector_store_ids for attachment search
        if self.context.request.vector_store_ids:
            follow_up_params["vector_store_ids"] = self.context.request.vector_store_ids

        # Preserve structured_output_schema for JSON responses
        if self.context.request.structured_output_schema:
            follow_up_params["structured_output_schema"] = (
                self.context.request.structured_output_schema
            )

        # Execute follow-up with appropriate strategy
        follow_up_request = OpenAIRequest(**follow_up_params)
        follow_up_context = FlowContext(
            request=follow_up_request,
            client=self.context.client,
            tools=self.context.tools,
            tool_executor=self.context.tool_executor,
            start_time=asyncio.get_event_loop().time(),
            timeout_remaining=self.context.timeout_remaining,
        )

        # Use same strategy type for follow-up
        if isinstance(self, BackgroundFlowStrategy):
            follow_up_strategy: BaseFlowStrategy = BackgroundFlowStrategy(
                follow_up_context
            )
        else:
            follow_up_strategy = StreamingFlowStrategy(follow_up_context)

        return await follow_up_strategy.execute()


class BackgroundFlowStrategy(BaseFlowStrategy):
    """Strategy for background/polling execution."""

    async def execute(self) -> Dict[str, Any]:
        """Execute background flow with polling."""
        # Build API parameters
        api_params = self.context.request.to_api_format()
        api_params["background"] = True
        api_params["stream"] = False  # Explicitly set to False for background mode

        if self.context.tools:
            api_params["tools"] = self.context.tools
            api_params["parallel_tool_calls"] = self.context.request.parallel_tool_calls

        # Only add reasoning parameters if the model supports them
        capability = model_capabilities.get(self.context.request.model)
        if (
            self.context.request.reasoning_effort
            and capability
            and capability.supports_reasoning_effort
        ):
            api_params["reasoning"] = {"effort": self.context.request.reasoning_effort}
            # Remove the flat reasoning_effort parameter that was included by to_api_format()
            api_params.pop("reasoning_effort", None)

        # Create initial response
        logger.info(
            f"[ADAPTER] Starting OpenAI responses.create at {time.strftime('%H:%M:%S')}"
        )
        api_start_time = time.time()
        initial_response = await self.context.client.responses.create(**api_params)
        api_end_time = time.time()
        logger.info(
            f"[ADAPTER] OpenAI responses.create completed in {api_end_time - api_start_time:.2f}s"
        )
        response_id = initial_response.id

        # Check if the initial response is already completed (for tests/immediate responses)
        initial_job = initial_response
        if hasattr(initial_job, "status") and initial_job.status == "completed":
            # Handle immediately completed response
            content = self._extract_content_from_output(initial_job)
            function_calls = self._extract_function_calls(initial_job)

            if function_calls:
                all_output_items = self._collect_all_output_items(initial_job)
                return await self._handle_function_calls(
                    function_calls, response_id, all_output_items
                )

            # Validate structured output
            self._validate_structured_output(content)

            immediate_result: Dict[str, Any] = {
                "content": content,
                "response_id": response_id,
            }

            if self.context.request.return_debug:
                immediate_result["_debug_tools"] = self.context.tools

            return immediate_result

        # Poll for completion with exponential backoff
        delay = INITIAL_POLL_DELAY_SEC
        start_poll_time = asyncio.get_event_loop().time()

        logger.info(
            f"Starting background polling for {response_id}, timeout={self.context.timeout_remaining}s"
        )

        while True:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                logger.warning(f"[CANCEL] Polling cancelled for {response_id}")
                logger.info(
                    f"[CANCEL] Active tasks during OpenAI poll cancel: {len(asyncio.all_tasks())}"
                )
                logger.info("[CANCEL] Re-raising from OpenAI polling loop")
                # Re-raise to propagate cancellation properly
                raise

            elapsed = asyncio.get_event_loop().time() - start_poll_time

            # Check if we've exceeded timeout
            if elapsed >= self.context.timeout_remaining:
                logger.info(
                    f"Timeout reached: elapsed={elapsed:.1f}s >= timeout={self.context.timeout_remaining}s"
                )
                break

            # Check status
            logger.debug(
                f"[ADAPTER] Polling OpenAI response status for {response_id} at {time.strftime('%H:%M:%S')} (elapsed: {elapsed:.1f}s)"
            )
            job = await self.context.client.responses.retrieve(response_id)
            logger.debug(
                f"[ADAPTER] OpenAI response {response_id} status: {job.status}"
            )

            if job.status == "completed":
                # Extract content
                content = self._extract_content_from_output(job)

                # Check for function calls
                function_calls = self._extract_function_calls(job)
                if function_calls:
                    all_output_items = self._collect_all_output_items(job)
                    return await self._handle_function_calls(
                        function_calls, response_id, all_output_items
                    )

                # Validate structured output
                self._validate_structured_output(content)

                # Return final result
                polled_result: Dict[str, Any] = {
                    "content": content,
                    "response_id": response_id,
                }

                if self.context.request.return_debug:
                    polled_result["_debug_tools"] = self.context.tools

                return polled_result

            elif job.status == "incomplete":
                # Handle incomplete response
                content = self._extract_content_from_output(job)
                return {
                    "content": content,
                    "response_id": response_id,
                    "status": "incomplete",
                }

            elif job.status not in ["queued", "in_progress"]:
                # Handle failed/cancelled/unknown status
                error_msg = getattr(job, "error", {})
                if isinstance(error_msg, dict):
                    error_detail = error_msg.get("message", "Unknown error")
                else:
                    error_detail = str(error_msg) if error_msg else "Unknown error"

                raise RuntimeError(
                    f"Run failed with status: {job.status}. Error: {error_detail}"
                )

            # Update delay with exponential backoff
            delay = min(delay * 1.8, MAX_POLL_INTERVAL_SEC)
            # Add jitter to prevent thundering herd
            delay += random.uniform(0, 0.2)

        # Timeout reached
        final_elapsed = asyncio.get_event_loop().time() - start_poll_time
        raise TimeoutException(
            f"Job {response_id} timed out after {final_elapsed:.1f}s",
            elapsed=final_elapsed,
            timeout=self.context.request.timeout,
        )


class StreamingFlowStrategy(BaseFlowStrategy):
    """Strategy for streaming execution."""

    async def execute(self) -> Dict[str, Any]:
        """Execute streaming flow."""
        # Build API parameters
        api_params = self.context.request.to_api_format()
        api_params["stream"] = True
        api_params["background"] = False  # Explicitly set to False for streaming mode

        if self.context.tools:
            api_params["tools"] = self.context.tools
            api_params["parallel_tool_calls"] = self.context.request.parallel_tool_calls

        # Only add reasoning parameters if the model supports them
        capability = model_capabilities.get(self.context.request.model)
        if (
            self.context.request.reasoning_effort
            and capability
            and capability.supports_reasoning_effort
        ):
            api_params["reasoning"] = {"effort": self.context.request.reasoning_effort}
            # Remove the flat reasoning_effort parameter that was included by to_api_format()
            api_params.pop("reasoning_effort", None)

        # Create streaming response
        stream = await asyncio.wait_for(
            self.context.client.responses.create(**api_params),
            timeout=self.context.timeout_remaining,
        )

        # Process stream
        response_id = None
        content_parts = []
        function_calls = []
        function_call_ids: Set[str] = set()
        event_count = 0

        async for event in stream:
            event_count += 1

            # Capture response ID from various locations
            if response_id is None:
                if (
                    hasattr(event, "id")
                    and isinstance(event.id, str)
                    and event.id.startswith("resp_")
                ):
                    response_id = event.id
                    logger.debug(f"Captured response ID from event.id: {response_id}")
                elif hasattr(event, "response_id"):
                    response_id = event.response_id
                    logger.debug(
                        f"Captured response ID from event.response_id: {response_id}"
                    )

            # Handle different event types
            if hasattr(event, "type"):
                if event.type in (
                    "response.delta",
                    "ResponseOutputTextDelta",
                ) and hasattr(event, "delta"):
                    content_parts.append(event.delta)
                elif event.type == "response.output_text" and hasattr(event, "text"):
                    content_parts.append(event.text)
                elif event.type in ("response.tool_call", "tool_call", "function_call"):
                    # Collect function calls, avoiding duplicates
                    call_id = getattr(event, "call_id", None)
                    if call_id and call_id not in function_call_ids:
                        function_call_ids.add(call_id)
                        function_calls.append(
                            {
                                "type": "function_call",
                                "call_id": call_id,
                                "name": getattr(event, "name", None),
                                "arguments": getattr(event, "arguments", "{}"),
                            }
                        )
            # Fallback for other structures
            elif hasattr(event, "output_text") and event.output_text:
                content_parts.append(event.output_text)
            elif hasattr(event, "text") and event.text:
                content_parts.append(event.text)

        content = "".join(content_parts)

        # Handle function calls if present
        if function_calls:
            logger.info(
                f"{self.context.request.model} streaming returned {len(function_calls)} function calls"
            )

            # For streaming with functions, we need to preserve the context differently
            all_output_items = function_calls.copy()
            return await self._handle_function_calls(
                function_calls, response_id or "", all_output_items
            )

        # Validate structured output
        self._validate_structured_output(content)

        # Return result
        logger.info(
            f"Streaming complete: events={event_count}, content_length={len(content)}, response_id={response_id}"
        )

        result: Dict[str, Any] = {"content": content, "response_id": response_id}

        if self.context.request.return_debug:
            result["_debug_tools"] = self.context.tools

        return result


class FlowOrchestrator:
    """Orchestrates the execution flow for OpenAI requests."""

    def __init__(self, tool_dispatcher=None):
        """Initialize orchestrator with optional custom tool dispatcher.

        Args:
            tool_dispatcher: Optional custom function for dispatching tools.
                           If not provided, uses BuiltInToolDispatcher.
        """
        if tool_dispatcher is None:
            # Default to built-in tools
            self.tool_dispatcher = lambda: BuiltInToolDispatcher()
        else:
            self.tool_dispatcher = lambda: tool_dispatcher

    async def run(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run the orchestrated flow.

        Args:
            request_data: Raw request data including model, messages, etc.

        Returns:
            Response dictionary with content and metadata.
        """
        try:
            # 1. Pre-process request to handle model capabilities
            request_data = self._preprocess_request(request_data)

            # Extract API key before creating request object
            api_key = request_data.pop("_api_key", None)

            # 2. Validate and create request object
            request = OpenAIRequest(**request_data)

            # 3. Get process-safe client
            client = await OpenAIClientFactory.get_instance(api_key)

            # 3. Determine execution strategy
            use_background = self._should_use_background(request)

            # Log unknown models
            if request.model not in model_capabilities:
                logger.warning(
                    f"Unknown model '{request.model}' - defaulting to background mode"
                )

            # Override request based on strategy
            if use_background:
                request.background = True
                request.stream = False
            else:
                request.background = False
                request.stream = True

            # 4. Create context
            start_time = asyncio.get_event_loop().time()

            # Initialize tool executor with dispatcher
            if hasattr(self.tool_dispatcher(), "__call__"):
                # It's a function dispatcher
                tool_executor = ToolExecutor(self.tool_dispatcher())
            else:
                # It's a BuiltInToolDispatcher instance
                dispatcher_instance = self.tool_dispatcher()
                dispatcher_instance.vector_store_ids = request.vector_store_ids
                tool_executor = ToolExecutor(dispatcher_instance.dispatch)

            context = FlowContext(
                request=request,
                client=client,
                tools=[],  # Will be built by strategy
                tool_executor=tool_executor,
                start_time=start_time,
                timeout_remaining=request.timeout,
            )

            # 5. Select and execute strategy
            if use_background:
                strategy: BaseFlowStrategy = BackgroundFlowStrategy(context)
            else:
                strategy = StreamingFlowStrategy(context)

            # Build tools within strategy
            context.tools = strategy._build_tools_list()

            # 6. Execute and handle errors
            return await strategy.execute()

        except asyncio.TimeoutError:
            raise TimeoutException(
                "Request timed out", elapsed=request.timeout, timeout=request.timeout
            )
        except Exception as e:
            # Handle specific OpenAI errors
            if hasattr(e, "status_code"):
                if e.status_code in [504, 524]:
                    raise GatewayTimeoutException(e.status_code, request.model)
                elif e.status_code == 429:
                    raise AdapterException(
                        ErrorCategory.RATE_LIMIT, str(e), e.status_code
                    )
                elif e.status_code in [401, 403]:
                    raise AdapterException(
                        ErrorCategory.FATAL_CLIENT, str(e), e.status_code
                    )
                elif e.status_code >= 500:
                    raise AdapterException(
                        ErrorCategory.TRANSIENT_API, str(e), e.status_code
                    )

            # Let other errors propagate
            raise

    def _should_use_background(self, request: OpenAIRequest) -> bool:
        """Determine if background mode should be used."""
        # Check model capabilities if available
        if request.model in model_capabilities:
            capability = model_capabilities[request.model]

            # Force background for models that require it
            if capability.force_background:
                return True

            # Use background for long timeouts or models without streaming
            if (
                request.timeout > STREAM_TIMEOUT_THRESHOLD
                or not capability.supports_streaming
            ):
                return True
        else:
            # Unknown model - default to safe background mode
            return True

        # User preference
        return request.background

    def _preprocess_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Pre-process request to handle model-specific requirements."""
        # Make a copy to avoid modifying original
        data = request_data.copy()
        model = data.get("model", "")

        # Check if model requires background mode
        if model in model_capabilities:
            capability = model_capabilities[model]

            # Force background for models that require it
            if capability.force_background:
                data["background"] = True
                data["stream"] = False

            # Handle timeout-based background selection
            elif data.get("timeout", 300) > STREAM_TIMEOUT_THRESHOLD:
                data["background"] = True
                data["stream"] = False

            # Apply default reasoning_effort if not provided
            if capability.supports_reasoning_effort and "reasoning_effort" not in data:
                if capability.default_reasoning_effort:
                    data["reasoning_effort"] = capability.default_reasoning_effort

        return data
