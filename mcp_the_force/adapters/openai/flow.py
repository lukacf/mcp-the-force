"""Flow orchestration for OpenAI adapter using the native Responses API."""

import asyncio
import copy
import logging
import random
import json
import jsonschema
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from uuid import uuid4

from .client import OpenAIClientFactory
from .models import OpenAIRequest, OPENAI_MODEL_CAPABILITIES
from ..protocol import CallContext, ToolCall
from ..errors import (
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
from ..memory_search_declaration import create_search_history_declaration_openai

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
        """Build the tools list for the API request."""
        tools = []
        capability = OPENAI_MODEL_CAPABILITIES.get(self.context.request.model)
        logger.debug(f"[FLOW_ORCHESTRATOR] Building tools for model: {self.context.request.model}")
        logger.debug(f"[FLOW_ORCHESTRATOR] Capability found: {capability is not None}")
        if not capability:
            return []

        logger.debug(f"[FLOW_ORCHESTRATOR] capability.supports_custom_tools: {capability.supports_custom_tools}")
        if capability.supports_custom_tools:
            disable_memory_search = self.context.request.disable_memory_search
            logger.debug(f"[FLOW_ORCHESTRATOR] disable_memory_search: {disable_memory_search}")
            logger.debug(f"[FLOW_ORCHESTRATOR] not disable_memory_search: {not disable_memory_search}")
            if not self.context.request.disable_memory_search:
                logger.debug("[FLOW_ORCHESTRATOR] Adding search_project_history tool")
                tools.append(create_search_history_declaration_openai())
            else:
                logger.debug("[FLOW_ORCHESTRATOR] NOT adding search_project_history tool - memory search disabled")
            if self.context.request.tools:
                tools.extend(self.context.request.tools)

        if capability.supports_web_search and capability.web_search_tool:
            tools.append({"type": capability.web_search_tool})

        if self.context.request.vector_store_ids and capability.native_vector_store_provider == "openai":
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
                    f"Added file_search tool with {len(openai_vector_stores)} OpenAI vector stores"
                )
            else:
                logger.debug("No OpenAI vector stores available for file_search tool")
        elif self.context.request.vector_store_ids:
            logger.debug(f"Model {self.context.request.model} does not support OpenAI vector stores, skipping file_search tool")

        logger.debug(f"[FLOW_ORCHESTRATOR] Final tools list length: {len(tools)}")
        return tools

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
        capability = OPENAI_MODEL_CAPABILITIES.get(request.model)
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
        capability = OPENAI_MODEL_CAPABILITIES.get(model)
        if capability and capability.supports_reasoning_effort:
            if "reasoning_effort" not in data and capability.default_reasoning_effort:
                data["reasoning_effort"] = capability.default_reasoning_effort
