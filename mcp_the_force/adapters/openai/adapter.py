"""Protocol-based OpenAI adapter using native OpenAI SDK."""

import logging
import json
from typing import Any, Dict, List, Union

from ..protocol import CallContext, ToolDispatcher
from ...unified_session_cache import UnifiedSessionCache
from ...utils.image_loader import load_images, ImageLoadError
from ...utils.image_formatter import format_for_openai
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

    def __init__(self, model: str = "gpt-5.2"):
        """Initialize OpenAI adapter.

        Args:
            model: OpenAI model name (e.g., "gpt-5.2", "gpt-5.2-pro", "gpt-4.1")

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
                    ctx.project, ctx.session_id
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

            # Handle images if provided - convert prompt to content array
            images_param = getattr(params, "images", None)
            input_content: Union[str, List[Dict[str, Any]]] = prompt
            if images_param:
                # Check vision capability BEFORE loading images
                if not self.capabilities.supports_vision:
                    raise ValueError(
                        f"Model '{self.model_name}' does not support vision/image inputs. "
                        f"Remove the 'images' parameter or use a vision-capable model."
                    )
                logger.info(
                    f"[OPENAI] Loading {len(images_param)} images for vision request"
                )
                try:
                    loaded_images = await load_images(images_param)
                except ImageLoadError as e:
                    # Re-raise with clearer context for users
                    raise ValueError(
                        f"Failed to load images for vision request: {e}"
                    ) from e
                except Exception as e:
                    logger.error(f"[OPENAI] Unexpected error loading images: {e}")
                    raise ValueError(
                        f"Failed to load images: {type(e).__name__}: {e}"
                    ) from e
                # Build content array with text + images
                input_content = [{"type": "text", "text": prompt}]
                input_content.extend(format_for_openai(loaded_images))
                logger.info(f"[OPENAI] Added {len(loaded_images)} images to request")

            # Build request data for FlowOrchestrator using Responses API format
            request_data = {
                "model": self.capabilities.model_name,  # Use the actual model name from capabilities
                "input": input_content,
                "instructions": instructions,
                "previous_response_id": previous_response_id,
                "vector_store_ids": ctx.vector_store_ids,
                "structured_output_schema": structured_output_schema,
                "disable_history_search": getattr(
                    params, "disable_history_search", False
                ),
                "session_id": ctx.session_id,
                "project": ctx.project,
                "tool": ctx.tool,
                "_api_key": self._api_key,
                **kwargs,  # Pass through any other kwargs like timeout, etc.
            }

            # Only include reasoning_effort/temperature if explicitly provided.
            # This allows _preprocess_request to apply model-specific defaults.
            reasoning_effort = getattr(params, "reasoning_effort", None)
            if reasoning_effort is not None:
                request_data["reasoning_effort"] = reasoning_effort

            temperature = getattr(params, "temperature", None)
            if temperature is not None:
                request_data["temperature"] = temperature

            # Debug: Check disable_history_search parameter
            disable_history_search = getattr(params, "disable_history_search", False)
            logger.debug(
                f"[OPENAI_ADAPTER] params.disable_history_search = {disable_history_search}"
            )
            logger.debug(
                f"[OPENAI_ADAPTER] request_data disable_history_search = {request_data.get('disable_history_search')}"
            )

            # Create and run flow orchestrator
            orchestrator = FlowOrchestrator(tool_dispatcher=tool_dispatcher)
            result = await orchestrator.run(request_data)

            # Store response_id in session for continuity
            if ctx.session_id and "response_id" in result:
                await UnifiedSessionCache.set_response_id(
                    ctx.project, ctx.session_id, result["response_id"]
                )
                # Also store that we're using OpenAI native format
                await UnifiedSessionCache.set_api_format(
                    ctx.project, ctx.session_id, "openai_native"
                )
                logger.debug(
                    f"Saved response_id {result['response_id']} for session {ctx.session_id}"
                )

            return result

        except Exception as e:
            logger.error(f"OpenAI adapter error: {e}")
            raise
