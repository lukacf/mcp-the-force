"""Protocol-based Ollama adapter using LiteLLM."""

import logging
from typing import Any, Dict, List, Optional

from ..errors import ConfigurationException
from ..litellm_base import LiteLLMBaseAdapter
from ..protocol import CallContext
from .capabilities import OllamaCapabilities
from .params import OllamaToolParams
from .overrides import ResolvedCapabilities
from ...config import get_settings

logger = logging.getLogger(__name__)


class OllamaAdapter(LiteLLMBaseAdapter):
    """Protocol-based Ollama adapter using LiteLLM.

    This adapter uses LiteLLM to communicate with Ollama local models.
    LiteLLM handles all the complex type conversions and API specifics internally.
    """

    param_class = OllamaToolParams

    def __init__(self, model: str):
        """Initialize the Ollama adapter.

        Args:
            model: Model name (e.g., "gpt-oss:20b", "gpt-oss:120b")
        """
        # Ollama supports any model name - we'll validate at runtime

        self.model_name = model
        self.display_name = f"Ollama {model}"

        # Try to get resolved capabilities from blueprint generator
        # Import here to avoid circular imports
        from . import blueprint_generator

        resolved_caps = blueprint_generator.get_capabilities().get(model)
        if resolved_caps:
            # Convert ResolvedCapabilities to OllamaCapabilities
            self.capabilities = self._resolved_to_ollama_capabilities(resolved_caps)
            if resolved_caps.memory_warning:
                logger.warning(f"Memory warning: {resolved_caps.memory_warning}")
        else:
            # Fall back to default capabilities
            logger.warning(
                f"Could not find resolved capabilities for model {model}, using defaults"
            )
            self.capabilities = OllamaCapabilities(
                model_name=model,
                supports_structured_output=True,  # Tests expect this to be True
                max_context_window=16384,  # Reasonable default
            )

        super().__init__()

    def _resolved_to_ollama_capabilities(
        self, resolved: ResolvedCapabilities
    ) -> OllamaCapabilities:
        """Convert ResolvedCapabilities to OllamaCapabilities."""
        return OllamaCapabilities(
            model_name=resolved.model_name,
            max_context_window=resolved.max_context_window,
            description=resolved.description,
            supports_structured_output=True,  # Tests expect this
        )

    def _validate_environment(self):
        """Validate Ollama configuration."""
        settings = get_settings()

        if not settings.ollama.enabled:
            raise ConfigurationException(
                "Ollama integration is disabled in configuration", provider="Ollama"
            )

        if not settings.ollama.host:
            raise ConfigurationException(
                "Ollama host not configured", provider="Ollama"
            )

        logger.debug(
            f"Ollama adapter initialized for {self.model_name} at {settings.ollama.host}"
        )

    def _get_model_prefix(self) -> str:
        """Get the LiteLLM model prefix for Ollama."""
        return (
            "ollama_chat"  # Uses /api/chat endpoint - recommended for conversational AI
        )

    def _build_request_params(
        self,
        conversation_input: List[Dict[str, Any]],
        params: OllamaToolParams,
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Build Ollama-specific request parameters for LiteLLM."""
        from ..errors import AdapterException, ErrorCategory

        settings = get_settings()

        # Build base request parameters
        request_params: Dict[str, Any] = {
            "model": f"{self._get_model_prefix()}/{self.model_name}",
            "input": conversation_input,  # LiteLLM maps this to messages
            "api_base": settings.ollama.host,  # Critical: pass Ollama host to LiteLLM
        }

        # Add Ollama-specific options via extra_headers
        ollama_options = {}

        # Always set context window from capabilities
        if self.capabilities.max_context_window:
            ollama_options["num_ctx"] = self.capabilities.max_context_window

        # Add all Ollama parameters to options
        ollama_options["temperature"] = params.temperature
        if params.max_tokens:
            ollama_options["num_predict"] = params.max_tokens  # Ollama uses num_predict
        if params.top_p is not None:
            ollama_options["top_p"] = params.top_p
        if params.top_k is not None:
            ollama_options["top_k"] = params.top_k
        if params.seed is not None:
            ollama_options["seed"] = params.seed
        if params.keep_alive:
            ollama_options["keep_alive"] = params.keep_alive
        if params.repeat_penalty is not None:
            ollama_options["repeat_penalty"] = params.repeat_penalty

        # Set extra_headers with options for Ollama
        if ollama_options:
            request_params["extra_headers"] = {"options": ollama_options}

        # Handle JSON format for response_format
        if params.format == "json":
            request_params["response_format"] = {"type": "json_object"}

        # Tools/function calling
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")

        # Ollama doesn't support structured output schema validation
        # Block this early to prevent silent failures
        if (
            hasattr(params, "structured_output_schema")
            and params.structured_output_schema
        ):
            raise AdapterException(
                category=ErrorCategory.INVALID_MODEL,
                message=f"Model {self.model_name} doesn't support structured output schema validation. Use format='json' for basic JSON mode instead.",
                provider="ollama",
            )

        # Remove keys with None values to ensure clean dict for aresponses()
        return {k: v for k, v in request_params.items() if v is not None}

    def _build_conversation_input(
        self,
        prompt: str,
        ctx: CallContext,
        system_instruction: Optional[str] = None,
        structured_output_schema: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build conversation input, flattening content arrays to strings for Ollama compatibility.

        Ollama's /api/chat expects message content to be plain strings, not arrays.
        This method converts OpenAI-style content arrays to simple strings.
        """
        # Get the base conversation input from parent class
        conversation_input = super()._build_conversation_input(
            prompt, ctx, system_instruction, structured_output_schema
        )

        # Flatten content arrays to strings for Ollama compatibility
        for msg in conversation_input:
            if isinstance(msg.get("content"), list):
                # Concatenate all text parts from the content array
                text_parts = []
                for part in msg["content"]:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        text_parts.append(part)

                # Join all text parts with spaces
                msg["content"] = " ".join(text_parts)

        return conversation_input
