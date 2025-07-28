"""Standardized error hierarchy for all adapters.

Based on the OpenAI adapter's error handling, this module provides
a unified error structure that all adapters should use.
"""

from enum import Enum, auto
from typing import Optional, Any


class ErrorCategory(Enum):
    """Categories of errors for intelligent recovery strategies."""

    TRANSIENT_API = auto()  # Server-side errors (5xx), safe to retry
    FATAL_CLIENT = auto()  # Client-side errors (4xx), indicates a bug, do not retry
    RATE_LIMIT = auto()  # API rate limit (429), retry with backoff
    TIMEOUT = auto()  # Network or gateway timeout, suggest background mode
    TOOL_EXECUTION = auto()  # An error occurred within a local tool call
    PARSING = auto()  # Error parsing API responses
    AUTHENTICATION = auto()  # Authentication or authorization errors
    INVALID_MODEL = auto()  # Invalid or unsupported model specified
    CONFIGURATION = auto()  # Missing or invalid configuration


class AdapterException(Exception):
    """Base exception for adapter errors with categorization."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        status_code: int = 0,
        provider: Optional[str] = None,
    ):
        # Include provider in message if specified
        if provider:
            super().__init__(f"[{provider}] [{category.name}] {message}")
        else:
            super().__init__(f"[{category.name}] {message}")
        self.category = category
        self.status_code = status_code
        self.provider = provider


class TimeoutException(AdapterException):
    """Specific exception for timeout scenarios."""

    def __init__(
        self,
        message: str,
        elapsed: float,
        timeout: float,
        provider: Optional[str] = None,
    ):
        super().__init__(ErrorCategory.TIMEOUT, message, provider=provider)
        self.elapsed = elapsed
        self.timeout = timeout


class GatewayTimeoutException(AdapterException):
    """Specific exception for gateway timeouts (504, 524)."""

    def __init__(
        self, status_code: int, model_name: str, provider: Optional[str] = None
    ):
        message = (
            f"Gateway timeout ({status_code}) after ~100-180s of idle time. "
            f"Model: {model_name}. This happens when non-streaming requests "
            f"take too long to produce output. The request may still be processing "
            f"server-side. For {model_name}, background mode should have been "
            f"used automatically - this error suggests a configuration issue."
        )
        super().__init__(ErrorCategory.TIMEOUT, message, status_code, provider=provider)
        self.model_name = model_name


class ToolExecutionException(AdapterException):
    """Exception for tool execution failures."""

    def __init__(
        self,
        tool_name: str,
        error: Exception,
        provider: Optional[str] = None,
    ):
        message = f"Tool '{tool_name}' failed: {error}"
        super().__init__(ErrorCategory.TOOL_EXECUTION, message, provider=provider)
        self.tool_name = tool_name
        self.original_error = error


class ResponseParsingException(AdapterException):
    """Exception for response parsing failures."""

    def __init__(
        self,
        message: str,
        response_data: Optional[Any] = None,
        provider: Optional[str] = None,
    ):
        super().__init__(ErrorCategory.PARSING, message, provider=provider)
        self.response_data = response_data


class AuthenticationException(AdapterException):
    """Exception for authentication/authorization failures."""

    def __init__(self, message: str, provider: Optional[str] = None):
        super().__init__(
            ErrorCategory.AUTHENTICATION, message, status_code=401, provider=provider
        )


class InvalidModelException(AdapterException):
    """Exception for invalid or unsupported model."""

    def __init__(
        self,
        model: str,
        supported_models: list[str],
        provider: Optional[str] = None,
    ):
        message = (
            f"Unsupported model: {model}. "
            f"Supported models: {', '.join(supported_models)}"
        )
        super().__init__(
            ErrorCategory.INVALID_MODEL, message, status_code=400, provider=provider
        )
        self.model = model
        self.supported_models = supported_models


class ConfigurationException(AdapterException):
    """Exception for configuration issues."""

    def __init__(self, message: str, provider: Optional[str] = None):
        super().__init__(
            ErrorCategory.CONFIGURATION, message, status_code=500, provider=provider
        )


class RateLimitException(AdapterException):
    """Exception for rate limit errors."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[float] = None,
        provider: Optional[str] = None,
    ):
        super().__init__(
            ErrorCategory.RATE_LIMIT, message, status_code=429, provider=provider
        )
        self.retry_after = retry_after
