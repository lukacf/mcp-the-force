"""Protocol-based OpenAI adapter using native OpenAI SDK."""

import logging
import json
from typing import Any, Dict

from ..protocol import CallContext, ToolDispatcher
from ...unified_session_cache import UnifiedSessionCache
from .flow import FlowOrchestrator
from .definitions import OpenAIToolParams, OPENAI_MODEL_CAPABILITIES

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
            # Build input for Responses API format
            # The prompt is the user's input

            # Extract system instructions
            from ...prompts import get_developer_prompt

            instructions = get_developer_prompt(self.model_name)

            # Load previous_response_id from session if continuing
            previous_response_id = None
            if ctx.session_id:
                previous_response_id = await UnifiedSessionCache.get_response_id(
                    ctx.session_id
                )
                if previous_response_id:
                    logger.info(
                        f"Continuing session {ctx.session_id} with response_id: {previous_response_id}"
                    )

            # Prepare structured output schema
            structured_output_schema = getattr(params, "structured_output_schema", None)
            if structured_output_schema and isinstance(structured_output_schema, str):
                try:
                    structured_output_schema = json.loads(structured_output_schema)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse structured_output_schema as JSON: {structured_output_schema}"
                    )
                    structured_output_schema = None

            # Build request data for FlowOrchestrator using Responses API format
            request_data = {
                "model": self.model_name,
                "input": prompt,
                "instructions": instructions,
                "previous_response_id": previous_response_id,
                "vector_store_ids": ctx.vector_store_ids,
                "reasoning_effort": getattr(params, "reasoning_effort", None),
                "temperature": getattr(params, "temperature", None),
                "structured_output_schema": structured_output_schema,
                "disable_memory_search": getattr(
                    params, "disable_memory_search", False
                ),
                "session_id": ctx.session_id,
                "_api_key": self._api_key,
                **kwargs,  # Pass through any other kwargs like timeout, etc.
            }

            # Create and run flow orchestrator
            orchestrator = FlowOrchestrator(tool_dispatcher=tool_dispatcher)
            result = await orchestrator.run(request_data)

            # Store response_id in session for continuity
            if ctx.session_id and "response_id" in result:
                await UnifiedSessionCache.set_response_id(
                    ctx.session_id, result["response_id"]
                )
                # Also store that we're using OpenAI native format
                await UnifiedSessionCache.set_api_format(
                    ctx.session_id, "openai_native"
                )
                logger.debug(
                    f"Saved response_id {result['response_id']} for session {ctx.session_id}"
                )

            return result

        except Exception as e:
            logger.error(f"OpenAI adapter error: {e}")
            raise
