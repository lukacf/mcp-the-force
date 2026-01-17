"""Flow orchestration for OpenAI adapter using the native Responses API."""

import asyncio
import copy
import logging
import random
import json
import jsonschema
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, cast
from dataclasses import dataclass
from uuid import uuid4

from .client import OpenAIClientFactory
from .models import OpenAIRequest
from .definitions import get_model_capability
from ..protocol import CallContext, ToolCall
from ..errors import (
    AdapterException,
    ErrorCategory,
    TimeoutException,
    GatewayTimeoutException,
    RetryWithReducedContextException,
)
from .constants import (
    INITIAL_POLL_DELAY_SEC,
    MAX_POLL_INTERVAL_SEC,
    STREAM_TIMEOUT_THRESHOLD,
)

logger = logging.getLogger(__name__)


@dataclass
class FlowContext:
    """Context passed between flow stages."""

    request: OpenAIRequest
    client: Any  # AsyncOpenAI
    tools: List[Dict[str, Any]]
    tool_dispatcher: Any
    session_id: str
    project: str
    tool: str
    vector_store_ids: Optional[List[str]]
    start_time: float
    timeout_remaining: float


class BaseFlowStrategy(ABC):
    """Base strategy for flow execution using the Responses API."""

    def __init__(self, context: FlowContext):
        self.context = context

    @abstractmethod
    async def execute(self) -> Dict[str, Any]:
        """Execute the flow and return the result."""
        pass

    def _add_additional_properties_recursively(self, schema_node: Any) -> None:
        """
        Recursively traverses a JSON schema to add OpenAI-required properties:
        1. 'additionalProperties: false' to all objects
        2. 'required' array listing all properties for objects
        """
        if not isinstance(schema_node, dict):
            return

        # If the current node is an object schema
        if schema_node.get("type") == "object":
            # Add additionalProperties: false if not present
            if "additionalProperties" not in schema_node:
                schema_node["additionalProperties"] = False

            # Add required array if object has properties but no required array
            if "properties" in schema_node and "required" not in schema_node:
                # All properties are required by default for OpenAI
                schema_node["required"] = list(schema_node["properties"].keys())

        # Recurse into properties of an object
        if "properties" in schema_node:
            for prop in schema_node["properties"].values():
                self._add_additional_properties_recursively(prop)

        # Recurse into items of an array
        if "items" in schema_node:
            self._add_additional_properties_recursively(schema_node["items"])

        # Recurse into anyOf, allOf, oneOf definitions
        for key in ["anyOf", "allOf", "oneOf"]:
            if key in schema_node:
                for sub_schema in schema_node[key]:
                    self._add_additional_properties_recursively(sub_schema)

    def _prepare_api_params(self) -> Dict[str, Any]:
        """Prepare API parameters with any necessary transformations."""
        api_params = self.context.request.to_api_format()

        # Transform structured output schema if present
        if "text" in api_params and "format" in api_params["text"]:
            format_spec = api_params["text"]["format"]
            if format_spec.get("type") == "json_schema" and "schema" in format_spec:
                # Deep copy the schema to avoid modifying the original
                schema = copy.deepcopy(format_spec["schema"])
                # Apply OpenAI's requirement for additionalProperties: false
                self._add_additional_properties_recursively(schema)
                format_spec["schema"] = schema

        return api_params

    def _build_tools_list(self) -> List[Dict[str, Any]]:
        """Build the tools list for the API request using the tool_dispatcher."""
        capability = get_model_capability(self.context.request.model)
        logger.debug(
            f"[FLOW_ORCHESTRATOR] Building tools for model: {self.context.request.model}"
        )
        if not capability:
            return []

        # FIXED: Use the tool_dispatcher to get the correct tools (including search_task_files)
        # The dispatcher handles custom tools (search_project_history, search_task_files)
        tools = self.context.tool_dispatcher.get_tool_declarations(
            capabilities=capability,
            disable_history_search=self.context.request.disable_history_search,
        )
        logger.debug(f"[FLOW_ORCHESTRATOR] Got {len(tools)} tools from dispatcher")

        # Add any additional tools from the request
        if self.context.request.tools:
            tools.extend(self.context.request.tools)

        # Add provider-specific native tools
        if capability.supports_web_search and capability.web_search_tool:
            tools.append({"type": capability.web_search_tool})

        # Add native OpenAI file_search if vector stores are present and model supports it
        if (
            self.context.request.vector_store_ids
            and capability.native_vector_store_provider == "openai"
        ):
            # Filter to only include OpenAI vector stores (those starting with 'vs_')
            openai_vector_stores = [
                vs_id
                for vs_id in self.context.request.vector_store_ids
                if vs_id.startswith("vs_")
            ]
            if openai_vector_stores:
                tools.append(
                    {
                        "type": "file_search",
                        "vector_store_ids": openai_vector_stores,
                    }
                )
                logger.debug(
                    f"[FLOW_ORCHESTRATOR] Added native file_search tool with {len(openai_vector_stores)} OpenAI vector stores"
                )
            else:
                logger.debug(
                    "[FLOW_ORCHESTRATOR] No OpenAI vector stores available for file_search tool"
                )
        elif self.context.request.vector_store_ids:
            logger.debug(
                f"[FLOW_ORCHESTRATOR] Model {self.context.request.model} does not support OpenAI vector stores, skipping file_search tool"
            )

        logger.debug(f"[FLOW_ORCHESTRATOR] Final tools list length: {len(tools)}")

        # DEBUG: Log exact tools being passed for deep research models
        if "deep-research" in self.context.request.model:
            logger.error(
                f"[DEBUG] Deep research model {self.context.request.model} tools:"
            )
            for i, tool in enumerate(tools):
                logger.error(f"[DEBUG] Tool {i}: {tool}")
            logger.error("[DEBUG] Capability flags:")
            logger.error(f"[DEBUG]   supports_tools: {capability.supports_tools}")
            logger.error(
                f"[DEBUG]   supports_web_search: {capability.supports_web_search}"
            )
            logger.error(
                f"[DEBUG]   supports_live_search: {capability.supports_live_search}"
            )
            logger.error(f"[DEBUG]   web_search_tool: '{capability.web_search_tool}'")
            logger.error(
                f"[DEBUG]   native_vector_store_provider: {capability.native_vector_store_provider}"
            )

        return cast(List[Dict[str, Any]], tools)

    def _extract_content_from_output(self, response: Any) -> str:
        """Extract text content from the response object's output array."""
        if hasattr(response, "output_text"):
            return str(response.output_text)

        text_parts = []
        if hasattr(response, "output"):
            for item in response.output:
                if getattr(item, "type", "") == "message":
                    for content_item in getattr(item, "content", []):
                        if getattr(content_item, "type", "") == "output_text":
                            text_parts.append(getattr(content_item, "text", ""))
        return "".join(text_parts)

    def _extract_function_calls(self, response: Any) -> List[Any]:
        """Extract function calls from the response object's output array."""
        if not hasattr(response, "output"):
            return []
        return [
            item
            for item in response.output
            if getattr(item, "type", "") == "function_call"
        ]

    def _validate_structured_output(self, content: str) -> str:
        """Validate and clean JSON output against a schema."""
        if not self.context.request.structured_output_schema:
            return content
        try:
            from ...utils.json_extractor import extract_json

            clean_json = extract_json(content)
            parsed = json.loads(clean_json)
            jsonschema.validate(parsed, self.context.request.structured_output_schema)
            return clean_json
        except (jsonschema.ValidationError, json.JSONDecodeError, ValueError) as e:
            raise AdapterException(
                ErrorCategory.PARSING, f"Structured output validation failed: {e}"
            )

    def _extract_usage_info(self, response: Any) -> Dict[str, Any]:
        """Extract usage information from OpenAI response."""
        usage = {}
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            usage = {
                "input_tokens": getattr(u, "input_tokens", None),
                "output_tokens": getattr(u, "output_tokens", None),
                "total_tokens": getattr(u, "total_tokens", None),
            }
            reasoning_tokens = getattr(u, "reasoning_tokens", None)
            if reasoning_tokens is not None:
                usage["reasoning_tokens"] = reasoning_tokens
        return usage

    async def _handle_function_calls(
        self, function_calls: List[Any], response_id: str
    ) -> Dict[str, Any]:
        """Execute tools and orchestrate the follow-up API call."""
        logger.info(
            f"Executing {len(function_calls)} tool calls for response {response_id}"
        )

        tool_calls = [
            ToolCall(tool_name=c.name, tool_args=c.arguments, tool_call_id=c.call_id)
            for c in function_calls
        ]
        call_context = CallContext(
            session_id=self.context.session_id,
            project=self.context.project,
            tool=self.context.tool,
            vector_store_ids=self.context.vector_store_ids,
        )
        tool_results = await self.context.tool_dispatcher.execute_batch(
            tool_calls, call_context
        )

        # The new input is just the list of tool outputs. The server maintains state.
        follow_up_input = [
            {
                "type": "function_call_output",
                "call_id": call.tool_call_id,
                "output": result,
            }
            for call, result in zip(tool_calls, tool_results)
        ]

        # Create a new request for the follow-up, preserving key parameters
        follow_up_request_data = self.context.request.model_dump(
            exclude={"input", "previous_response_id"}
        )
        follow_up_request_data.update(
            {
                "input": follow_up_input,
                "previous_response_id": response_id,
            }
        )

        follow_up_request = OpenAIRequest(**follow_up_request_data)

        follow_up_context = FlowContext(
            request=follow_up_request,
            client=self.context.client,
            tools=self.context.tools,
            tool_dispatcher=self.context.tool_dispatcher,
            session_id=self.context.session_id,
            project=self.context.project,
            tool=self.context.tool,
            vector_store_ids=self.context.vector_store_ids,
            start_time=asyncio.get_event_loop().time(),
            timeout_remaining=self.context.timeout_remaining,
        )

        # Use the same strategy type (streaming/background) for the follow-up
        strategy = self.__class__(follow_up_context)
        return await strategy.execute()


class BackgroundFlowStrategy(BaseFlowStrategy):
    """Strategy for background/polling execution."""

    async def execute(self) -> Dict[str, Any]:
        api_params = self._prepare_api_params()
        if self.context.tools:
            api_params["tools"] = self.context.tools

        # DEBUG: Log exact API request for token analysis
        import os
        from ...utils.token_counter import count_tokens

        debug_file = f".mcp-the-force/debug_api_request_{self.context.session_id}.json"
        os.makedirs(os.path.dirname(debug_file), exist_ok=True)

        # Calculate actual tokens that will be sent to API
        api_content_parts = []
        if "input" in api_params:
            api_content_parts.append(api_params["input"])
        if "instructions" in api_params:
            api_content_parts.append(api_params["instructions"])
        if "messages" in api_params:
            for msg in api_params["messages"]:
                if isinstance(msg, dict) and "content" in msg:
                    api_content_parts.append(msg["content"])

        actual_api_tokens = count_tokens(api_content_parts)

        # Debug JSON file saving removed to reduce clutter
        logger.debug(
            f"[OPENAI] API request with {actual_api_tokens:,} tokens for session {self.context.session_id}"
        )

        initial_response = await self.context.client.responses.create(**api_params)
        response_id = initial_response.id

        if initial_response.status == "completed":
            job = initial_response
        else:
            delay = INITIAL_POLL_DELAY_SEC
            start_poll_time = asyncio.get_event_loop().time()
            while True:
                await asyncio.sleep(delay)
                elapsed = asyncio.get_event_loop().time() - start_poll_time
                if elapsed >= self.context.timeout_remaining:
                    raise TimeoutException(
                        f"Job {response_id} timed out",
                        elapsed,
                        self.context.request.timeout,
                    )

                job = await self.context.client.responses.retrieve(response_id)
                if job.status == "completed":
                    break
                if job.status not in ["queued", "in_progress"]:
                    error = getattr(job, "error", None)
                    error_message = "Unknown error"
                    if error:
                        # Handle both object and dict forms
                        if hasattr(error, "message"):
                            error_message = error.message
                        elif isinstance(error, dict):
                            error_message = error.get("message", "Unknown error")
                        else:
                            error_message = str(error)

                    # Check for incomplete_details when status is "incomplete"
                    incomplete_details = getattr(job, "incomplete_details", None)
                    if incomplete_details:
                        reason = None
                        if hasattr(incomplete_details, "reason"):
                            reason = incomplete_details.reason
                        elif isinstance(incomplete_details, dict):
                            reason = incomplete_details.get("reason")

                        if reason:
                            logger.warning(
                                f"[INCOMPLETE_RESPONSE] Job {response_id} incomplete. "
                                f"Reason: {reason}. "
                                f"Session: {self.context.session_id}"
                            )
                            error_message = f"{reason}"

                            # For max_output_tokens, signal retry with reduced context
                            if reason == "max_output_tokens":
                                raise RetryWithReducedContextException(
                                    reason=reason,
                                )
                            else:
                                logger.info(
                                    f"[INCOMPLETE_RESPONSE] Context retry not applicable for "
                                    f"incomplete reason: {reason}"
                                )

                    raise AdapterException(
                        ErrorCategory.TRANSIENT_API,
                        f"Run failed with status {job.status}: {error_message}",
                    )
                delay = min(delay * 1.8 + random.uniform(0, 0.2), MAX_POLL_INTERVAL_SEC)

        function_calls = self._extract_function_calls(job)
        if function_calls:
            return await self._handle_function_calls(function_calls, response_id)

        content = self._extract_content_from_output(job)
        content = self._validate_structured_output(content)

        # Log actual usage for debug comparison with predictions
        usage_info = self._extract_usage_info(job)
        if usage_info.get("input_tokens") is not None:
            logger.info(
                f"[ACTUAL_USAGE] Session {self.context.session_id}: "
                f"input_tokens={usage_info['input_tokens']:,}, "
                f"output_tokens={usage_info.get('output_tokens', 0):,}, "
                f"reasoning_tokens={usage_info.get('reasoning_tokens', 0):,}"
            )

        result = {"content": content, "response_id": response_id}
        if self.context.request.return_debug:
            result["_debug_tools"] = self.context.tools
        return result


class StreamingFlowStrategy(BaseFlowStrategy):
    """Strategy for streaming execution."""

    async def execute(self) -> Dict[str, Any]:
        api_params = self._prepare_api_params()
        if self.context.tools:
            api_params["tools"] = self.context.tools

        # DEBUG: Log exact API request for token analysis (streaming)
        import os
        from ...utils.token_counter import count_tokens

        debug_file = (
            f".mcp-the-force/debug_api_request_streaming_{self.context.session_id}.json"
        )
        os.makedirs(os.path.dirname(debug_file), exist_ok=True)

        # Calculate actual tokens that will be sent to API
        api_content_parts = []
        if "input" in api_params:
            api_content_parts.append(api_params["input"])
        if "instructions" in api_params:
            api_content_parts.append(api_params["instructions"])
        if "messages" in api_params:
            for msg in api_params["messages"]:
                if isinstance(msg, dict) and "content" in msg:
                    api_content_parts.append(msg["content"])

        actual_api_tokens = count_tokens(api_content_parts)

        # Debug JSON file saving removed to reduce clutter
        logger.debug(
            f"[OPENAI] Streaming API request with {actual_api_tokens:,} tokens for session {self.context.session_id}"
        )

        stream = await asyncio.wait_for(
            self.context.client.responses.create(**api_params),
            timeout=self.context.timeout_remaining,
        )

        response_id, content_parts, function_calls = None, [], []
        final_response_obj = None

        async for event in stream:
            if (
                response_id is None
                and hasattr(event, "id")
                and event.id.startswith("resp_")
            ):
                response_id = event.id
            if hasattr(event, "type") and event.type == "response.delta":
                content_parts.append(event.delta)
            if hasattr(event, "type") and event.type == "response.final_response":
                final_response_obj = event.response

        if final_response_obj:
            function_calls = self._extract_function_calls(final_response_obj)

            # Check for incomplete status in streaming response
            if getattr(final_response_obj, "status", None) == "incomplete":
                incomplete_details = getattr(
                    final_response_obj, "incomplete_details", None
                )
                reason = "Unknown reason"
                if incomplete_details:
                    if hasattr(incomplete_details, "reason"):
                        reason = incomplete_details.reason
                    elif isinstance(incomplete_details, dict):
                        reason = incomplete_details.get("reason", "Unknown reason")

                logger.warning(
                    f"[INCOMPLETE_RESPONSE] Streaming response incomplete. "
                    f"Reason: {reason}. "
                    f"Session: {self.context.session_id}"
                )

                # For max_output_tokens, signal retry with reduced context
                if reason == "max_output_tokens":
                    raise RetryWithReducedContextException(
                        reason=reason,
                    )
                else:
                    logger.info(
                        f"[INCOMPLETE_RESPONSE] Context retry not applicable for "
                        f"incomplete reason: {reason}"
                    )

                raise AdapterException(
                    ErrorCategory.TRANSIENT_API,
                    f"Streaming response incomplete: {reason}",
                )

        if function_calls:
            # The full response object is needed to get complete tool call details
            if not response_id and final_response_obj:
                response_id = final_response_obj.id
            if not response_id:
                raise AdapterException(
                    ErrorCategory.PARSING,
                    "Could not determine response_id for stream with tool calls.",
                )
            return await self._handle_function_calls(function_calls, response_id)

        content = "".join(content_parts)
        content = self._validate_structured_output(content)

        # Log actual usage for debug comparison with predictions (streaming)
        if final_response_obj:
            usage_info = self._extract_usage_info(final_response_obj)
            if usage_info.get("input_tokens") is not None:
                logger.info(
                    f"[ACTUAL_USAGE] Session {self.context.session_id}: "
                    f"input_tokens={usage_info['input_tokens']:,}, "
                    f"output_tokens={usage_info.get('output_tokens', 0):,}, "
                    f"reasoning_tokens={usage_info.get('reasoning_tokens', 0):,}"
                )

        result = {"content": content, "response_id": response_id}
        if self.context.request.return_debug:
            result["_debug_tools"] = self.context.tools
        return result


class FlowOrchestrator:
    """Orchestrates the execution flow for OpenAI requests."""

    def __init__(self, tool_dispatcher):
        self.tool_dispatcher = tool_dispatcher

    async def run(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            session_id = request_data.pop("session_id", f"sess_{uuid4().hex}")
            project = request_data.pop("project", "")
            tool = request_data.pop("tool", "")
            api_key = request_data.pop("_api_key", None)

            self._preprocess_request(request_data)
            request = OpenAIRequest(**request_data)

            client = await OpenAIClientFactory.get_instance(api_key)
            use_background = self._should_use_background(request)
            request.background = use_background
            request.stream = not use_background

            context = FlowContext(
                request=request,
                client=client,
                tools=[],
                tool_dispatcher=self.tool_dispatcher,
                session_id=session_id,
                project=project,
                tool=tool,
                vector_store_ids=request.vector_store_ids,
                start_time=asyncio.get_event_loop().time(),
                timeout_remaining=request.timeout,
            )

            strategy = (
                BackgroundFlowStrategy(context)
                if use_background
                else StreamingFlowStrategy(context)
            )
            context.tools = strategy._build_tools_list()

            return await strategy.execute()

        except asyncio.TimeoutError:
            raise TimeoutException(
                "Request timed out", request.timeout, request.timeout
            )
        except Exception as e:
            if hasattr(e, "status_code"):
                status = e.status_code
                if status in [504, 524]:
                    raise GatewayTimeoutException(
                        status, request_data.get("model", "unknown")
                    )
                if status == 429:
                    raise AdapterException(ErrorCategory.RATE_LIMIT, str(e), status)
                if status >= 500:
                    raise AdapterException(ErrorCategory.TRANSIENT_API, str(e), status)
                if status >= 400:
                    raise AdapterException(ErrorCategory.FATAL_CLIENT, str(e), status)
            raise

    def _should_use_background(self, request: OpenAIRequest) -> bool:
        capability = get_model_capability(request.model)
        if capability:
            if capability.force_background:
                return True
            if not capability.supports_streaming:
                return True
        if request.timeout > STREAM_TIMEOUT_THRESHOLD:
            return True
        return request.background

    def _preprocess_request(self, data: Dict[str, Any]):
        """Applies model-specific defaults before validation."""
        model = data.get("model", "")
        capability = get_model_capability(model)
        if capability and capability.supports_reasoning_effort:
            # Only apply capability default when reasoning_effort is not provided.
            # If user explicitly provides any value (including "medium"), respect it.
            if "reasoning_effort" not in data and capability.default_reasoning_effort:
                data["reasoning_effort"] = capability.default_reasoning_effort
