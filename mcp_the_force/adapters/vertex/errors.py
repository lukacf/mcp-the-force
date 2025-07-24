"""Error hierarchy for Vertex adapter."""

from enum import Enum, auto
from typing import Optional


class ErrorCategory(Enum):
    """Categories of errors for intelligent recovery strategies."""

    TRANSIENT_ERROR = auto()  # Server-side errors, safe to retry.
    FATAL_CLIENT = auto()  # Client-side errors, indicates a bug, do not retry.
    RATE_LIMIT = auto()  # API rate limit, retry with backoff.
    TIMEOUT = auto()  # Network or gateway timeout.
    TOOL_EXECUTION = auto()  # An error occurred within a local tool call.
    PARSING = auto()  # Error parsing API responses
    INVALID_REQUEST = auto()  # Invalid request parameters
    CONFIGURATION = auto()  # Missing or invalid configuration
    INITIALIZATION = auto()  # Failed to initialize adapter or client


class AdapterException(Exception):
    """Base exception for adapter errors with categorization."""

    def __init__(
        self,
        message: str,
        error_category: ErrorCategory,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(f"[{error_category.name}] {message}")
        self.error_category = error_category
        self.original_error = original_error
