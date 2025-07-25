"""Protocol-based OpenAI adapter using native OpenAI SDK.

This adapter implements the MCPAdapter protocol without inheritance,
using the OpenAI SDK directly (not LiteLLM) since LiteLLM's purpose
is to translate TO OpenAI format.
"""

import logging
from typing import Any, Dict

from ..protocol import CallContext, ToolDispatcher
from ..params import OpenAIToolParams
from ...unified_session_cache import unified_session_cache
from .flow import FlowOrchestrator
from .models import OPENAI_MODEL_CAPABILITIES

logger = logging.getLogger(__name__)


class OpenAIProtocolAdapter:
    """OpenAI adapter implementing MCPAdapter protocol.

    This adapter uses the native OpenAI SDK and preserves all the
    battle-tested flow orchestration logic for handling long-running
    background jobs, tool execution, and complex error scenarios.
    """

    # Protocol requirements
    param_class = OpenAIToolParams

    def __init__(self, model: str = "o3"):
        """Initialize OpenAI adapter.

        Args:
            model: OpenAI model name (e.g., "o3", "o3-pro", "gpt-4.1")

        Raises:
            ValueError: If model is not supported
        """
        if model not in OPENAI_MODEL_CAPABILITIES:
            raise ValueError(
                f"Unknown OpenAI model: {model}. "
                f"Supported models: {list(OPENAI_MODEL_CAPABILITIES.keys())}"
            )

        self.model_name = model
        self.display_name = f"OpenAI {model}"

        # Get pre-built capabilities for this model
        self.capabilities = OPENAI_MODEL_CAPABILITIES[model]

        # Get API key from settings
        from ...config import get_settings

        settings = get_settings()
        self._api_key = settings.openai_api_key
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not configured")

    async def generate(
        self,
        prompt: str,
        params: OpenAIToolParams,
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate response using OpenAI SDK via FlowOrchestrator.

        Args:
            prompt: User prompt
            params: Validated OpenAIToolParams instance
            ctx: Call context with session_id and vector_store_ids
            tool_dispatcher: Tool execution interface
            **kwargs: Additional parameters

        Returns:
            Dict with "content" and optionally "response_id"
        """
        try:
            # Build messages from kwargs or create new
            messages = kwargs.get("messages")
            if not messages:
                # Check for system instruction
                system_instruction = kwargs.get("system_instruction")
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

            # Load previous_response_id from session if continuing
            previous_response_id = None
            if ctx.session_id:
                previous_response_id = await unified_session_cache.get_response_id(
                    ctx.session_id
                )
                if previous_response_id:
                    logger.info(
                        f"Continuing session {ctx.session_id} with response_id: {previous_response_id}"
                    )

            # Parse structured_output_schema if it's a string
            structured_output_schema = getattr(params, "structured_output_schema", None)
            if structured_output_schema and isinstance(structured_output_schema, str):
                import json

                try:
                    structured_output_schema = json.loads(structured_output_schema)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse structured_output_schema as JSON: {structured_output_schema}"
                    )
                    structured_output_schema = None

            # Build request data for FlowOrchestrator
            request_data = {
                "model": self.model_name,
                "messages": messages,
                "reasoning_effort": getattr(params, "reasoning_effort", None),
                "vector_store_ids": ctx.vector_store_ids,
                "structured_output_schema": structured_output_schema,
                "disable_memory_search": getattr(
                    params, "disable_memory_search", False
                ),
                "session_id": ctx.session_id,  # FlowOrchestrator expects this
                "_api_key": self._api_key,
                "previous_response_id": previous_response_id,
                "return_debug": kwargs.get("return_debug", False),
                "max_output_tokens": kwargs.get("max_output_tokens"),
                "timeout": kwargs.get("timeout", 300),
            }

            # Add any extra kwargs that might be needed
            for key, value in kwargs.items():
                if key not in request_data and key not in [
                    "messages",
                    "system_instruction",
                ]:
                    request_data[key] = value

            # Create and run flow orchestrator
            orchestrator = FlowOrchestrator(tool_dispatcher=tool_dispatcher)
            result = await orchestrator.run(request_data)

            # Store response_id in session for continuity
            if ctx.session_id and "response_id" in result:
                await unified_session_cache.set_response_id(
                    ctx.session_id, result["response_id"]
                )
                # Also store that we're using OpenAI native format
                await unified_session_cache.set_api_format(
                    ctx.session_id, "openai_native"
                )
                logger.debug(
                    f"Saved response_id {result['response_id']} for session {ctx.session_id}"
                )

            return result

        except Exception as e:
            logger.error(f"OpenAI adapter error: {e}")
            raise
