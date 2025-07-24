"""Error hierarchy for OpenAI adapter."""

from enum import Enum, auto
from typing import Optional


class ErrorCategory(Enum):
    """Categories of errors for intelligent recovery strategies."""

    TRANSIENT_API = auto()  # Server-side errors (5xx), safe to retry.
    FATAL_CLIENT = auto()  # Client-side errors (4xx), indicates a bug, do not retry.
    RATE_LIMIT = auto()  # API rate limit (429), retry with backoff.
    TIMEOUT = auto()  # Network or gateway timeout, suggest background mode.
    TOOL_EXECUTION = auto()  # An error occurred within a local tool call.
    PARSING = auto()  # Error parsing API responses


class AdapterException(Exception):
    """Base exception for adapter errors with categorization."""

    def __init__(self, category: ErrorCategory, message: str, status_code: int = 0):
        super().__init__(f"[{category.name}] {message}")
        self.category = category
        self.status_code = status_code


class TimeoutException(AdapterException):
    """Specific exception for timeout scenarios."""

    def __init__(self, message: str, elapsed: float, timeout: float):
        super().__init__(ErrorCategory.TIMEOUT, message)
        self.elapsed = elapsed
        self.timeout = timeout


class GatewayTimeoutException(AdapterException):
    """Specific exception for gateway timeouts (504, 524)."""

    def __init__(self, status_code: int, model_name: str):
        message = (
            f"Gateway timeout ({status_code}) after ~100-180s of idle time. "
            f"Model: {model_name}. This happens when non-streaming requests "
            f"take too long to produce output. The request may still be processing "
            f"server-side. For {model_name}, background mode should have been "
            f"used automatically - this error suggests a configuration issue."
        )
        super().__init__(ErrorCategory.TIMEOUT, message, status_code)
        self.model_name = model_name


class ToolExecutionException(AdapterException):
    """Exception for tool execution failures."""

    def __init__(self, tool_name: str, error: Exception):
        message = f"Tool '{tool_name}' failed: {error}"
        super().__init__(ErrorCategory.TOOL_EXECUTION, message)
        self.tool_name = tool_name
        self.original_error = error


class ResponseParsingException(AdapterException):
    """Exception for response parsing failures."""

    def __init__(self, message: str, response_data: Optional[dict] = None):
        super().__init__(ErrorCategory.PARSING, message)
        self.response_data = response_data
