"""Unit tests for OpenAI adapter error hierarchy."""

import pytest
from mcp_second_brain.adapters.openai.errors import (
    AdapterException,
    ErrorCategory,
    TimeoutException,
    GatewayTimeoutException,
    ToolExecutionException,
    ResponseParsingException,
)


@pytest.mark.unit
def test_adapter_exception_creation():
    """Verify that AdapterException correctly stores its properties."""
    exc = AdapterException(
        ErrorCategory.RATE_LIMIT, "Rate limit exceeded", status_code=429
    )
    assert exc.category == ErrorCategory.RATE_LIMIT
    assert exc.status_code == 429
    assert "RATE_LIMIT" in str(exc)
    assert "Rate limit exceeded" in str(exc)


@pytest.mark.unit
def test_timeout_exception():
    """Verify TimeoutException stores elapsed and timeout values."""
    exc = TimeoutException("Request timed out", elapsed=120.5, timeout=100.0)
    assert exc.category == ErrorCategory.TIMEOUT
    assert exc.elapsed == 120.5
    assert exc.timeout == 100.0
    assert "Request timed out" in str(exc)


@pytest.mark.unit
def test_gateway_timeout_exception():
    """Verify GatewayTimeoutException generates correct message."""
    exc = GatewayTimeoutException(status_code=504, model_name="o3-pro")
    assert exc.category == ErrorCategory.TIMEOUT
    assert exc.status_code == 504
    assert exc.model_name == "o3-pro"
    assert "Gateway timeout (504)" in str(exc)
    assert "o3-pro" in str(exc)
    assert "background mode should have been used" in str(exc)


@pytest.mark.unit
def test_tool_execution_exception():
    """Verify ToolExecutionException captures tool failures."""
    original_error = ValueError("Invalid arguments")
    exc = ToolExecutionException("search_memory", original_error)
    assert exc.category == ErrorCategory.TOOL_EXECUTION
    assert exc.tool_name == "search_memory"
    assert exc.original_error == original_error
    assert "Tool 'search_memory' failed" in str(exc)
    assert "Invalid arguments" in str(exc)


@pytest.mark.unit
def test_response_parsing_exception():
    """Verify ResponseParsingException can store response data."""
    response_data = {"status": "error", "message": "Malformed response"}
    exc = ResponseParsingException("Failed to parse output", response_data)
    assert exc.category == ErrorCategory.PARSING
    assert exc.response_data == response_data
    assert "Failed to parse output" in str(exc)


@pytest.mark.unit
def test_error_category_enum():
    """Verify all error categories are defined."""
    categories = {cat.name for cat in ErrorCategory}
    expected = {
        "TRANSIENT_API",
        "FATAL_CLIENT",
        "RATE_LIMIT",
        "TIMEOUT",
        "TOOL_EXECUTION",
        "PARSING",
    }
    assert categories == expected
