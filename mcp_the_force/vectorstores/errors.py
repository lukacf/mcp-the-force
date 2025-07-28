"""Vector store exception hierarchy."""

from typing import Optional


class VectorStoreError(Exception):
    """Base exception for all vector store errors."""

    pass


class QuotaExceededError(VectorStoreError):
    """Raised when a quota limit is exceeded."""

    pass


class AuthError(VectorStoreError):
    """Raised when authentication fails."""

    pass


class UnsupportedFeatureError(VectorStoreError):
    """Raised when a requested feature is not supported by the provider."""

    pass


class TransientError(VectorStoreError):
    """Raised for temporary errors that may be retried.

    Attributes:
        retry_after: Optional seconds to wait before retrying
    """

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after
