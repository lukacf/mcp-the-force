"""Protocol-based Gemini adapter using LiteLLM."""

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from ..errors import InvalidModelException, ConfigurationException
from ..litellm_base import LiteLLMBaseAdapter
from ..protocol import CallContext, ToolDispatcher
from .definitions import GeminiToolParams, GEMINI_MODEL_CAPABILITIES
from ...config import get_settings

logger = logging.getLogger(__name__)


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


class GeminiAdapter(LiteLLMBaseAdapter):
    """Protocol-based Gemini adapter using LiteLLM.

    This adapter uses LiteLLM to communicate with Google's Gemini models via
    Vertex AI. LiteLLM handles all the complex type conversions and API
    specifics internally.
    """

    param_class = GeminiToolParams

    def __init__(self, model: str = "gemini-2.5-pro"):
        """Initialize the Gemini adapter."""
        if model not in GEMINI_MODEL_CAPABILITIES:
            raise InvalidModelException(
                model=model,
                supported_models=list(GEMINI_MODEL_CAPABILITIES.keys()),
                provider="Gemini",
            )

        self.model_name = model
        self.display_name = f"Gemini {model} (LiteLLM)"
        self.capabilities = GEMINI_MODEL_CAPABILITIES[model]
        self._auth_method = "uninitialized"  # To be set by _validate_environment

        super().__init__()

    def _validate_environment(self):
        """Validate Gemini/Vertex AI authentication in the correct order."""
        settings = get_settings()

        # 1. Service Account (via adc_credentials_path)
        if (
            settings.vertex.adc_credentials_path
            and settings.vertex.project
            and settings.vertex.location
        ):
            self._auth_method = "service_account"
            logger.info("Using Vertex AI with specified ADC credentials.")
            return

        # 2. Gemini API Key
        if settings.gemini and settings.gemini.api_key:
            if settings.vertex.project or settings.vertex.location:
                logger.warning(
                    "Both Gemini API key and Vertex AI config are present. "
                    "Prioritizing Gemini API key."
                )
            self._auth_method = "api_key"
            logger.info("Using Gemini API key.")
            return

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
            "1. Service Account: Set `vertex.adc_credentials_path`, `vertex.project`, and `vertex.location`.\n"
            "2. API Key: Set `gemini.api_key`.\n"
            "3. ADC: Run `gcloud auth application-default login` and set `vertex.project` and `vertex.location`.",
            provider="Gemini",
        )

    def _get_model_prefix(self) -> str:
        """Get the LiteLLM model prefix based on the auth method."""
        if self._auth_method == "api_key":
            return "google"  # Use 'google' for direct API key auth
        return "vertex_ai"  # Use 'vertex_ai' for all other auth methods

    def _build_request_params(
        self,
        conversation_input: List[Dict[str, Any]],
        params: GeminiToolParams,
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Build Gemini-specific request parameters."""
        request_params = {
            "model": f"{self._get_model_prefix()}/{self.model_name}",
            "input": conversation_input,
            "temperature": getattr(params, "temperature", 1.0),
        }

        settings = get_settings()

        # Add parameters based on the authentication method
        if self._auth_method == "api_key":
            if settings.gemini and settings.gemini.api_key:
                request_params["api_key"] = settings.gemini.api_key
        else:  # service_account, implicit_adc, fallback_adc
            if settings.vertex.project:
                request_params["vertex_project"] = settings.vertex.project
            if settings.vertex.location:
                request_params["vertex_location"] = settings.vertex.location

        # Add instructions if provided
        if hasattr(params, "instructions") and params.instructions:
            request_params["instructions"] = params.instructions

        # Add tools if any
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")

        # Add reasoning effort
        if hasattr(params, "reasoning_effort") and params.reasoning_effort:
            request_params["reasoning_effort"] = params.reasoning_effort
            logger.info(f"[GEMINI] Using reasoning_effort: {params.reasoning_effort}")

        # Add structured output schema
        if (
            hasattr(params, "structured_output_schema")
            and params.structured_output_schema
        ):
            request_params["response_format"] = {
                "type": "json_object",
                "response_schema": params.structured_output_schema,
                "enforce_validation": True,
            }
            logger.info("[GEMINI] Using structured output schema")

        # Add any extra kwargs that LiteLLM might use
        for key in ["max_tokens", "top_p", "frequency_penalty", "presence_penalty"]:
            if key in kwargs:
                request_params[key] = kwargs[key]

        return request_params

    async def generate(
        self,
        prompt: str,
        params: GeminiToolParams,
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate a response using LiteLLM with ADC error handling.

        Uses the base implementation with Gemini-specific overrides.
        """
        try:
            # Gemini doesn't support citations, so we override the result
            result = await super().generate(
                prompt=prompt,
                params=params,
                ctx=ctx,
                tool_dispatcher=tool_dispatcher,
                **kwargs,
            )

            # Ensure we don't return citations for Gemini
            result["citations"] = None
            return result
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
