"""Unit tests for adapter structure and protocol compliance.

These tests verify that adapters follow the MCPAdapter protocol and have the required interface.
They serve as a basic smoke test that the adapter modules are properly structured.

Note: Actual cancellation behavior testing requires integration tests with real API calls.
"""

import pytest
from unittest.mock import patch
from mcp_the_force.config import Settings, ProviderConfig


@pytest.fixture(autouse=True)
def mock_settings_for_adapters():
    """Auto-mock settings for all adapter structure tests."""
    mock_settings = Settings(
        vertex=ProviderConfig(project="test-project", location="us-central1"),
        gemini=ProviderConfig(api_key=None),
        xai=ProviderConfig(api_key="test-key"),
        openai=ProviderConfig(api_key="test-key"),
    )

    # Patch get_settings at multiple locations since adapters may import it differently
    with (
        patch("mcp_the_force.config.get_settings") as mock_get_settings1,
        patch(
            "mcp_the_force.adapters.google.adapter.get_settings"
        ) as mock_get_settings2,
    ):
        mock_get_settings1.return_value = mock_settings
        mock_get_settings2.return_value = mock_settings
        yield mock_settings


@pytest.mark.unit
def test_grok_adapter_protocol_compliance():
    """Verify that Grok (XAI) adapter follows MCPAdapter protocol."""
    from mcp_the_force.adapters.xai import GrokAdapter

    # Create an instance to check protocol compliance
    adapter = GrokAdapter("grok-3-beta")

    # Verify required attributes
    assert hasattr(adapter, "model_name")
    assert hasattr(adapter, "display_name")
    assert hasattr(adapter, "capabilities")
    assert hasattr(adapter, "param_class")
    assert hasattr(adapter, "generate")
    assert callable(adapter.generate)

    # Check that it has the right structure (duck typing)
    assert adapter.model_name == "grok-3-beta"
    assert adapter.display_name
    assert adapter.capabilities is not None
    assert adapter.param_class is not None


@pytest.mark.unit
def test_openai_adapter_protocol_compliance():
    """Verify that OpenAI adapter follows MCPAdapter protocol."""
    from mcp_the_force.adapters.openai import OpenAIProtocolAdapter

    # Create an instance to check protocol compliance
    adapter = OpenAIProtocolAdapter("o3")

    # Verify required attributes
    assert hasattr(adapter, "model_name")
    assert hasattr(adapter, "display_name")
    assert hasattr(adapter, "capabilities")
    assert hasattr(adapter, "param_class")
    assert hasattr(adapter, "generate")
    assert callable(adapter.generate)

    # Check that it has the right structure
    assert adapter.model_name == "o3"
    assert adapter.display_name
    assert adapter.capabilities is not None
    assert adapter.param_class is not None


@pytest.mark.unit
def test_gemini_adapter_protocol_compliance():
    """Verify that Gemini (Google) adapter follows MCPAdapter protocol."""
    from mcp_the_force.adapters.google import GeminiAdapter

    # Create an instance to check protocol compliance
    adapter = GeminiAdapter("gemini-2.5-pro")

    # Verify required attributes
    assert hasattr(adapter, "model_name")
    assert hasattr(adapter, "display_name")
    assert hasattr(adapter, "capabilities")
    assert hasattr(adapter, "param_class")
    assert hasattr(adapter, "generate")
    assert callable(adapter.generate)

    # Check that it has the right structure
    assert adapter.model_name == "gemini-2.5-pro"
    assert adapter.display_name
    assert adapter.capabilities is not None
    assert adapter.param_class is not None


@pytest.mark.unit
def test_all_adapters_follow_mcp_protocol():
    """Verify all adapters properly implement MCPAdapter protocol."""
    from mcp_the_force.adapters.xai import GrokAdapter
    from mcp_the_force.adapters.openai import OpenAIProtocolAdapter
    from mcp_the_force.adapters.google import GeminiAdapter

    # Create instances with sample models
    adapters = [
        GrokAdapter("grok-3-beta"),
        OpenAIProtocolAdapter("o3"),
        GeminiAdapter("gemini-2.5-pro"),
    ]

    for adapter in adapters:
        # Verify required protocol attributes
        assert hasattr(adapter, "model_name")
        assert hasattr(adapter, "display_name")
        assert hasattr(adapter, "capabilities")
        assert hasattr(adapter, "param_class")

        # Verify generate method
        assert hasattr(adapter, "generate")
        assert callable(adapter.generate)

        # Verify types
        assert isinstance(adapter.model_name, str)
        assert isinstance(adapter.display_name, str)
        assert adapter.capabilities is not None
        assert adapter.param_class is not None


@pytest.mark.unit
def test_adapter_registry_integration():
    """Test that adapters can be retrieved from the registry."""
    from mcp_the_force.adapters.registry import get_adapter_class, list_adapters

    # Check that we have registered adapters
    available = list_adapters()
    assert "openai" in available
    assert "google" in available
    assert "xai" in available

    # Check that we can get adapter classes
    openai_class = get_adapter_class("openai")
    assert openai_class is not None

    google_class = get_adapter_class("google")
    assert google_class is not None

    xai_class = get_adapter_class("xai")
    assert xai_class is not None

    # Verify they can be instantiated
    openai_adapter = openai_class("o3")
    assert openai_adapter.model_name == "o3"

    google_adapter = google_class("gemini-2.5-pro")
    assert google_adapter.model_name == "gemini-2.5-pro"

    xai_adapter = xai_class("grok-3-beta")
    assert xai_adapter.model_name == "grok-3-beta"
