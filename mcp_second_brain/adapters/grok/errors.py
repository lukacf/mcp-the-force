"""Error handling for Grok adapter."""

from enum import Enum
from typing import Optional


class ErrorCategory(Enum):
    """Categories of errors for better handling."""

    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    API_ERROR = "api_error"
    INVALID_REQUEST = "invalid_request"
    TIMEOUT = "timeout"
    NETWORK = "network"


class AdapterException(Exception):
    """Base exception for adapter errors with categorization."""

    def __init__(
        self,
        message: str,
        error_category: ErrorCategory = ErrorCategory.API_ERROR,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_category = error_category
        self.original_error = original_error
