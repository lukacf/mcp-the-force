"""Common errors for MCP The Force server."""


class UnsupportedStructuredOutputError(Exception):
    """Raised when a model doesn't support structured output schemas."""

    def __init__(self, model: str, message: str | None = None):
        if message is None:
            message = f"Model '{model}' does not support structured output schemas"
        super().__init__(message)
        self.model = model
