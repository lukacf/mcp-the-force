"""Unit tests for OpenAI adapter models and configuration."""

import pytest
from unittest.mock import patch
from pydantic import ValidationError
from mcp_the_force.adapters.openai.models import (
    ModelCapability,
    OpenAIRequest,
    model_capabilities,
)


@pytest.mark.unit
def test_model_capability_validation():
    """Test ModelCapability validation rules."""
    # Valid capability
    cap = ModelCapability(
        supports_streaming=True, force_background=False, context_window=200000
    )
    assert cap.supports_streaming is True
    assert cap.supports_web_search is False  # default value

    # Invalid context window
    with pytest.raises(ValidationError, match="context_window must be positive"):
        ModelCapability(
            supports_streaming=True, force_background=False, context_window=-1
        )


@pytest.mark.unit
def test_model_capabilities_defined():
    """Test that model capabilities are properly defined."""
    # Check that we have the expected models
    assert "o3" in model_capabilities
    assert "o3-pro" in model_capabilities
    assert "gpt-4.1" in model_capabilities
    assert "o4-mini" in model_capabilities

    # Check o3 capabilities
    o3_cap = model_capabilities["o3"]
    assert o3_cap.supports_streaming is True
    assert o3_cap.force_background is False
    assert o3_cap.supports_reasoning is True
    assert o3_cap.context_window == 200000

    # Check o3-pro capabilities
    o3_pro_cap = model_capabilities["o3-pro"]
    assert o3_pro_cap.supports_streaming is False
    assert o3_pro_cap.force_background is True
    assert o3_pro_cap.supports_reasoning is True

    # Check gpt-4.1 capabilities
    gpt4_cap = model_capabilities["gpt-4.1"]
    assert gpt4_cap.supports_streaming is True
    assert gpt4_cap.supports_web_search is True
    assert gpt4_cap.context_window == 1000000


@pytest.mark.unit
def test_openai_request_validation():
    """Test OpenAIRequest validation."""
    # Valid request
    req = OpenAIRequest(
        model="o3", messages=[{"role": "user", "content": "Hello"}], stream=True
    )
    assert req.model == "o3"
    assert req.stream is True

    # Invalid model
    with pytest.raises(ValidationError, match="Model 'unknown' is not defined"):
        OpenAIRequest(model="unknown", messages=[{"role": "user", "content": "Hello"}])

    # Invalid streaming for non-streaming model
    with pytest.raises(ValidationError, match="does not support streaming"):
        OpenAIRequest(
            model="o3-pro",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
        )

    # Invalid reasoning for non-reasoning model
    with pytest.raises(ValidationError, match="does not support reasoning"):
        OpenAIRequest(
            model="gpt-4.1",
            messages=[{"role": "user", "content": "Hello"}],
            reasoning_effort="high",
        )


@pytest.mark.unit
def test_openai_request_to_api_format():
    """Test conversion to API format."""
    # Request with all features for o3
    req1 = OpenAIRequest(
        model="o3",
        messages=[{"role": "user", "content": "Hello"}],
        reasoning_effort="high",
        parallel_tool_calls=True,
        return_debug=True,
        timeout=300,
        vector_store_ids=["vs_123"],
    )

    api_format1 = req1.to_api_format()
    assert "input" in api_format1  # messages converted to input
    assert "messages" not in api_format1
    assert api_format1["reasoning_effort"] == "high"  # kept for o3
    assert api_format1["parallel_tool_calls"] is True  # kept for o3
    # Internal parameters should be stripped
    assert "return_debug" not in api_format1
    assert "timeout" not in api_format1
    assert "vector_store_ids" not in api_format1

    # Request for model without certain capabilities
    req2 = OpenAIRequest(
        model="gpt-4.1",
        messages=[{"role": "user", "content": "Hello"}],
        parallel_tool_calls=True,  # supported
    )

    api_format2 = req2.to_api_format()
    assert api_format2["parallel_tool_calls"] is True  # kept for gpt-4.1
    assert "reasoning_effort" not in api_format2  # not provided


@pytest.mark.unit
def test_openai_request_with_mocked_capabilities():
    """Test OpenAIRequest with mocked model capabilities."""
    # Create a mock model with limited capabilities
    mock_caps = {
        "test-model": ModelCapability(
            supports_streaming=True,
            force_background=False,
            supports_reasoning=False,
            supports_parallel_tool_calls=False,
        )
    }

    with patch("mcp_the_force.adapters.openai.models.model_capabilities", mock_caps):
        # Valid request for test model
        req = OpenAIRequest(
            model="test-model",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,  # allowed
        )
        assert req.model == "test-model"

        # Convert to API format - parallel_tool_calls should be stripped
        req_with_tools = OpenAIRequest(
            model="test-model",
            messages=[{"role": "user", "content": "Hello"}],
            parallel_tool_calls=True,
        )
        api_format = req_with_tools.to_api_format()
        assert "parallel_tool_calls" not in api_format  # stripped

        # Reasoning should fail validation
        with pytest.raises(ValidationError, match="does not support reasoning"):
            OpenAIRequest(
                model="test-model",
                messages=[{"role": "user", "content": "Hello"}],
                reasoning_effort="high",
            )
