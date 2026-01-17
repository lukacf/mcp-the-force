"""Native Gemini adapter using google-genai SDK directly.

This adapter bypasses LiteLLM to use the google-genai SDK natively,
preserving thought_signature fields for Gemini 3+ models.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from ..errors import ConfigurationException
from ..protocol import CallContext, ToolDispatcher
from .definitions import GeminiToolParams, GEMINI_MODEL_CAPABILITIES
from .converters import (
    responses_to_contents,
    tools_to_gemini,
    extract_text_from_response,
    extract_function_calls,
)
from ...config import get_settings
from ...unified_session_cache import UnifiedSessionCache
from ...prompts import get_developer_prompt
from ...utils.image_loader import load_images, ImageLoadError
from ...utils.history_sanitizer import strip_images_from_history

logger = logging.getLogger(__name__)

# Client cache to avoid recreating clients
_client_cache: Dict[str, genai.Client] = {}


def setup_project_adc() -> str:
    """Set up Application Default Credentials for the current project.

    Returns:
        Path to the created ADC credentials file
    """
    # Get the project root (where config.yaml is)
    settings = get_settings()
    config_path = getattr(settings, "_config_path", None)
    if config_path:
        project_root = Path(config_path).parent
    else:
        project_root = Path.cwd()

    # Create .gcp directory if it doesn't exist
    gcp_dir = project_root / ".gcp"
    gcp_dir.mkdir(exist_ok=True)

    # ADC file path
    adc_path = gcp_dir / "adc-credentials.json"

    # Check if ADC already exists
    if adc_path.exists():
        logger.info(f"ADC already exists at {adc_path}")
        return str(adc_path)

    # Run gcloud auth to create ADC
    logger.info("Setting up Application Default Credentials...")
    logger.info("This will open a browser for authentication.")

    try:
        # Run gcloud auth application-default login
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "login"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise ConfigurationException(
                f"Failed to set up ADC: {result.stderr}", provider="Gemini"
            )

        # Copy the default ADC to project-specific location
        default_adc = (
            Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
        )
        if default_adc.exists():
            import shutil

            shutil.copy2(default_adc, adc_path)
            logger.info(f"ADC credentials saved to {adc_path}")

            # Update config.yaml to include the ADC path
            config_yaml_path = project_root / "config.yaml"
            if config_yaml_path.exists():
                logger.info(f"Please add the following to your {config_yaml_path}:")
                logger.info("providers:")
                logger.info("  vertex:")
                logger.info("    adc_credentials_path: .gcp/adc-credentials.json")

            return str(adc_path)
        else:
            raise ConfigurationException(
                "ADC setup completed but credentials file not found at expected location",
                provider="Gemini",
            )

    except FileNotFoundError:
        raise ConfigurationException(
            "gcloud CLI not found. Please install Google Cloud SDK: "
            "https://cloud.google.com/sdk/docs/install",
            provider="Gemini",
        )
    except Exception as e:
        raise ConfigurationException(
            f"Failed to set up ADC: {str(e)}", provider="Gemini"
        )


class GeminiAdapter:
    """Native Gemini adapter using google-genai SDK directly.

    This adapter uses the google-genai SDK to communicate with Google's Gemini
    models. It supports both Gemini API (via API key) and Vertex AI authentication.
    """

    param_class = GeminiToolParams

    def __init__(self, model: str = "gemini-3-pro-preview"):
        """Initialize the Gemini adapter.

        Args:
            model: Gemini model name (e.g., "gemini-3-pro-preview", "gemini-3-flash-preview").
        """
        self.model_name = model
        self.display_name = f"Gemini {model}"
        self._auth_method = "uninitialized"
        self._client: Optional[genai.Client] = None

        # Validate environment first
        self._validate_environment()

        # Load capabilities safely
        capabilities = GEMINI_MODEL_CAPABILITIES.get(model)
        if capabilities:
            self.capabilities = capabilities
        else:
            logger.warning(
                "Unknown Gemini model '%s', defaulting to gemini-3-pro-preview capabilities",
                model,
            )
            from .definitions import Gemini3ProPreviewCapabilities

            self.capabilities = Gemini3ProPreviewCapabilities()

    def _validate_environment(self):
        """Validate Gemini/Vertex AI authentication in the correct order.

        Priority order (Gemini API key first - simpler, more reliable):
        1. Gemini API Key (preferred)
        2. Service Account (via adc_credentials_path)
        3. Implicit ADC (GOOGLE_APPLICATION_CREDENTIALS)
        4. Fallback ADC (gcloud auth)
        """
        settings = get_settings()
        logger.debug(f"[DEBUG] Settings ID: {id(settings)}, Working dir: {os.getcwd()}")

        # Debug logging
        logger.debug("[DEBUG] Validating Gemini environment:")
        logger.debug(
            f"[DEBUG] vertex.adc_credentials_path = {settings.vertex.adc_credentials_path}"
        )
        logger.debug(f"[DEBUG] vertex.project = {settings.vertex.project}")
        logger.debug(f"[DEBUG] vertex.location = {settings.vertex.location}")
        logger.debug(f"[DEBUG] Has gemini attr? {hasattr(settings, 'gemini')}")
        if hasattr(settings, "gemini"):
            logger.debug(
                f"[DEBUG] gemini.api_key = {'SET' if settings.gemini.api_key else 'NOT SET'}"
            )

        # 1. Gemini API Key (PREFERRED - simpler, more reliable than Vertex AI)
        if settings.gemini and settings.gemini.api_key:
            if settings.vertex.project or settings.vertex.location:
                logger.debug(
                    "Both Gemini API key and Vertex AI config are present. "
                    "Using Gemini API key (preferred)."
                )
            self._auth_method = "api_key"
            logger.info("Using Gemini API key.")
            return

        # 2. Service Account (via adc_credentials_path)
        logger.debug(
            f"[DEBUG] Checking service account: adc={bool(settings.vertex.adc_credentials_path)}, project={bool(settings.vertex.project)}, location={bool(settings.vertex.location)}"
        )
        if (
            settings.vertex.adc_credentials_path
            and settings.vertex.project
            and settings.vertex.location
        ):
            self._auth_method = "service_account"
            logger.info("Using Vertex AI with specified ADC credentials.")
            return
        logger.debug("[DEBUG] Service account check failed, moving to next method")

        # 3. Implicit Application Default Credentials (ADC)
        if (
            "GOOGLE_APPLICATION_CREDENTIALS" in os.environ
            and settings.vertex.project
            and settings.vertex.location
        ):
            self._auth_method = "implicit_adc"
            logger.info(
                "Using Vertex AI with implicit Application Default Credentials."
            )
            return

        # 4. Fallback ADC check (no env var, but project/location set)
        if settings.vertex.project and settings.vertex.location:
            self._auth_method = "fallback_adc"
            logger.info("Using Vertex AI with gcloud ADC.")
            return

        raise ConfigurationException(
            "No valid Gemini/Vertex AI credentials found. Please configure one of the following:\n"
            "1. API Key: Set `gemini.api_key` or GEMINI_API_KEY env var (recommended).\n"
            "2. Service Account: Set `vertex.adc_credentials_path`, `vertex.project`, and `vertex.location`.\n"
            "3. ADC: Run `gcloud auth application-default login` and set `vertex.project` and `vertex.location`.",
            provider="Gemini",
        )

    def _get_client(self) -> genai.Client:
        """Get or create a google-genai client based on auth method."""
        # Create cache key based on auth method and settings
        settings = get_settings()
        cache_key = f"{self._auth_method}_{self.model_name}"

        if cache_key in _client_cache:
            return _client_cache[cache_key]

        if self._auth_method == "api_key":
            # Use Gemini API with API key
            client = genai.Client(api_key=settings.gemini.api_key)
        else:
            # Use Vertex AI
            client = genai.Client(
                vertexai=True,
                project=settings.vertex.project,
                location=settings.vertex.location,
            )

        _client_cache[cache_key] = client
        return client

    def _build_generation_config(
        self, params: GeminiToolParams, tools: List[types.Tool], **kwargs: Any
    ) -> types.GenerateContentConfig:
        """Build GenerateContentConfig from params."""
        config_kwargs: Dict[str, Any] = {}

        # Temperature
        if hasattr(params, "temperature") and params.temperature is not None:
            config_kwargs["temperature"] = params.temperature

        # System instruction
        system_instruction = kwargs.get("system_instruction")
        if not system_instruction:
            system_instruction = get_developer_prompt(self.model_name)
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        # Tools
        if tools:
            config_kwargs["tools"] = tools

        # Reasoning effort -> thinking config
        if hasattr(params, "reasoning_effort") and params.reasoning_effort:
            thinking_budget = self._get_thinking_budget(params.reasoning_effort)
            if thinking_budget:
                config_kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_budget=thinking_budget,
                )
                logger.info(
                    f"[GEMINI] Using reasoning_effort: {params.reasoning_effort} -> budget: {thinking_budget}"
                )

        # Structured output schema
        if (
            hasattr(params, "structured_output_schema")
            and params.structured_output_schema
        ):
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = params.structured_output_schema
            logger.info("[GEMINI] Using structured output schema")

        return types.GenerateContentConfig(**config_kwargs)

    def _get_thinking_budget(self, reasoning_effort: str) -> Optional[int]:
        """Map reasoning_effort to thinking budget tokens."""
        if not hasattr(self.capabilities, "reasoning_effort_map"):
            return None

        effort_map = self.capabilities.reasoning_effort_map
        return effort_map.get(reasoning_effort, effort_map.get("medium"))

    async def generate(
        self,
        prompt: str,
        params: GeminiToolParams,
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate a response using the native google-genai SDK.

        Args:
            prompt: User prompt
            params: GeminiToolParams instance
            ctx: Call context with session info
            tool_dispatcher: Tool dispatcher for function calls
            **kwargs: Additional arguments (system_instruction, etc.)

        Returns:
            Dict with "content" key containing the response text
        """
        try:
            client = self._get_client()

            # Load session history
            original_history: List[Dict[str, Any]] = []
            if ctx.session_id:
                original_history = await UnifiedSessionCache.get_history(
                    ctx.project, ctx.tool, ctx.session_id
                )
                logger.debug(
                    f"[GEMINI] Loaded {len(original_history)} history items for session {ctx.session_id}"
                )

            # Convert history to google-genai format
            contents = responses_to_contents(original_history)

            # Add current user message with optional images
            user_parts: List[types.Part] = [types.Part(text=prompt)]
            user_content_items: List[Dict[str, Any]] = [
                {"type": "text", "text": prompt}
            ]

            # Handle images if provided
            images_param = getattr(params, "images", None)
            if images_param:
                # Check vision capability BEFORE loading images
                if not self.capabilities.supports_vision:
                    raise ValueError(
                        f"Model '{self.capabilities.model_name}' does not support vision/image inputs. "
                        f"Remove the 'images' parameter or use a vision-capable model."
                    )
                logger.info(
                    f"[GEMINI] Loading {len(images_param)} images for vision request"
                )
                try:
                    loaded_images = await load_images(images_param)
                except ImageLoadError as e:
                    # Re-raise with clearer context for users
                    raise ValueError(
                        f"Failed to load images for vision request: {e}"
                    ) from e
                except Exception as e:
                    logger.error(f"[GEMINI] Unexpected error loading images: {e}")
                    raise ValueError(
                        f"Failed to load images: {type(e).__name__}: {e}"
                    ) from e
                for img in loaded_images:
                    # Add image as Part for API
                    user_parts.append(
                        types.Part.from_bytes(data=img.data, mime_type=img.mime_type)
                    )
                    # Add to content items for session history

                    user_content_items.append(
                        {
                            "type": "image",
                            "mime_type": img.mime_type,
                            "source": img.source,
                            "original_path": img.original_path,
                        }
                    )
                logger.info(f"[GEMINI] Added {len(loaded_images)} images to request")

            user_message = {
                "type": "message",
                "role": "user",
                "content": user_content_items,
            }
            contents.append(types.Content(role="user", parts=user_parts))

            # Get tool declarations
            disable_history_search = getattr(params, "disable_history_search", False)
            tools_openai = tool_dispatcher.get_tool_declarations(
                capabilities=self.capabilities,
                disable_history_search=disable_history_search,
            )
            tools_gemini = tools_to_gemini(tools_openai)

            # Build config
            config = self._build_generation_config(params, tools_gemini, **kwargs)

            # Make API call
            logger.info(
                f"[GEMINI] Calling {self.model_name} with {len(contents)} content items"
            )
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            # Handle tool calls if any
            tool_interactions: List[Dict[str, Any]] = []
            final_content, tool_interactions = await self._handle_tool_loop(
                client=client,
                response=response,
                contents=contents,
                config=config,
                tool_dispatcher=tool_dispatcher,
                ctx=ctx,
            )

            # Save session
            if ctx.session_id:
                await self._save_session(
                    ctx=ctx,
                    original_history=original_history,
                    user_message=user_message,
                    tool_interactions=tool_interactions,
                    final_content=final_content,
                )

            return {
                "content": final_content,
                "citations": None,  # Gemini doesn't support citations
            }

        except Exception as e:
            error_str = str(e).lower()
            # Check for various authentication-related errors
            if any(
                indicator in error_str
                for indicator in [
                    "permission denied",
                    "permission_denied",
                    "iam_permission_denied",
                    "aiplatform.endpoints.predict",
                    "403",
                    "unauthorized",
                    "authentication",
                    "credentials",
                ]
            ):
                # Check if this is an ADC issue
                settings = get_settings()
                if settings.vertex.project and not os.environ.get(
                    "GOOGLE_APPLICATION_CREDENTIALS"
                ):
                    logger.error("ADC authentication failed. No credentials found.")
                    logger.info(
                        "Would you like to set up Application Default Credentials?"
                    )
                    logger.info("Run: gcloud auth application-default login")
                    logger.info("Or use the setup_project_adc() helper function")

                    # Provide helpful error message
                    raise ConfigurationException(
                        "Google Cloud authentication failed. ADC not configured.\n"
                        "To fix this:\n"
                        "1. Run: gcloud auth application-default login\n"
                        "2. Add to config.yaml:\n"
                        "   providers:\n"
                        "     vertex:\n"
                        "       adc_credentials_path: .gcp/adc-credentials.json\n"
                        "3. Restart the server",
                        provider="Gemini",
                    ) from e

            # Re-raise other errors
            raise

    async def _handle_tool_loop(
        self,
        client: genai.Client,
        response: types.GenerateContentResponse,
        contents: List[types.Content],
        config: types.GenerateContentConfig,
        tool_dispatcher: ToolDispatcher,
        ctx: CallContext,
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Execute tool calls until model returns final text response.

        Preserves thought_signature natively via the SDK.

        Args:
            client: google-genai client
            response: Initial response from generate_content
            contents: Current conversation contents
            config: Generation config
            tool_dispatcher: Tool dispatcher
            ctx: Call context

        Returns:
            Tuple of (final_text_content, tool_interactions_for_history)
        """
        tool_interactions: List[Dict[str, Any]] = []
        max_iterations = 10  # Prevent infinite loops

        for iteration in range(max_iterations):
            # Extract function calls from response
            function_call_parts = extract_function_calls(response)

            if not function_call_parts:
                # No more tool calls - return final text
                final_text = extract_text_from_response(response)
                return final_text, tool_interactions

            logger.info(
                f"[GEMINI] Tool loop iteration {iteration + 1}: {len(function_call_parts)} function calls"
            )

            # Add model's response to contents (includes function calls with thought_signature)
            if response.candidates and response.candidates[0].content:
                contents.append(response.candidates[0].content)

            # Execute each function call and collect responses
            function_response_parts: List[types.Part] = []

            for fc_part in function_call_parts:
                fc = fc_part.function_call

                # Record function call in history (with thought_signature!)
                fc_history_item = {
                    "type": "function_call",
                    "name": fc.name,
                    "arguments": json.dumps(fc.args) if fc.args else "{}",
                    "call_id": fc.id,
                }
                if fc_part.thought_signature:
                    if isinstance(fc_part.thought_signature, bytes):
                        fc_history_item["thought_signature"] = (
                            fc_part.thought_signature.decode("utf-8")
                        )
                    else:
                        fc_history_item["thought_signature"] = str(
                            fc_part.thought_signature
                        )
                tool_interactions.append(fc_history_item)

                # Execute tool
                try:
                    args_str = json.dumps(fc.args) if fc.args else "{}"
                    result = await tool_dispatcher.execute(
                        tool_name=fc.name,
                        tool_args=args_str,
                        context=ctx,
                    )
                    result_str = str(result) if result is not None else ""
                except Exception as e:
                    logger.error(f"[GEMINI] Tool execution error: {e}")
                    result_str = f"Error executing tool: {str(e)}"

                # Record function output in history
                tool_interactions.append(
                    {
                        "type": "function_call_output",
                        "call_id": fc.id,
                        "name": fc.name,
                        "output": result_str,
                    }
                )

                # Build function response for API
                function_response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=fc.id,
                            name=fc.name,
                            response={"result": result_str},
                        )
                    )
                )

            # Add function responses as user turn
            contents.append(types.Content(role="user", parts=function_response_parts))

            # Continue conversation
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

        # Max iterations reached
        logger.warning(f"[GEMINI] Max tool loop iterations ({max_iterations}) reached")
        return extract_text_from_response(response), tool_interactions

    async def _save_session(
        self,
        ctx: CallContext,
        original_history: List[Dict[str, Any]],
        user_message: Dict[str, Any],
        tool_interactions: List[Dict[str, Any]],
        final_content: str,
    ) -> None:
        """Save updated session history."""
        updated_history = list(original_history)

        # Add user message
        updated_history.append(user_message)

        # Add tool interactions (function_call and function_call_output items)
        updated_history.extend(tool_interactions)

        # Add assistant response
        updated_history.append(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": final_content}],
            }
        )

        # Strip image data before saving to prevent context explosion on subsequent turns
        sanitized_history = strip_images_from_history(updated_history)

        await UnifiedSessionCache.set_history(
            ctx.project, ctx.tool, ctx.session_id, sanitized_history
        )
        logger.debug(
            f"[GEMINI] Saved {len(updated_history)} history items for session {ctx.session_id}"
        )
