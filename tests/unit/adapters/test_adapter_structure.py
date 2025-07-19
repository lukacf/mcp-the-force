"""Unit tests for adapter structure and imports.

These tests verify that adapters can be imported and have the required interface.
They serve as a basic smoke test that the adapter modules are properly structured.

Note: Actual cancellation behavior testing requires integration tests with real API calls.
"""

import pytest


@pytest.mark.unit
def test_grok_adapter_structure():
    """Verify that Grok adapter can be imported and has required methods."""
    from mcp_second_brain.adapters.grok import GrokAdapter
    from mcp_second_brain.adapters.base import BaseAdapter

    # Verify it's properly structured
    assert issubclass(GrokAdapter, BaseAdapter)
    assert hasattr(GrokAdapter, "generate")
    assert callable(GrokAdapter.generate)


@pytest.mark.unit
def test_openai_adapter_structure():
    """Verify that OpenAI adapter can be imported and has required methods."""
    from mcp_second_brain.adapters.openai import OpenAIAdapter
    from mcp_second_brain.adapters.base import BaseAdapter

    # Verify it's properly structured
    assert issubclass(OpenAIAdapter, BaseAdapter)
    assert hasattr(OpenAIAdapter, "generate")
    assert callable(OpenAIAdapter.generate)


@pytest.mark.unit
def test_vertex_adapter_structure():
    """Verify that Vertex adapter can be imported and has required methods."""
    from mcp_second_brain.adapters.vertex import VertexAdapter
    from mcp_second_brain.adapters.base import BaseAdapter

    # Verify it's properly structured
    assert issubclass(VertexAdapter, BaseAdapter)
    assert hasattr(VertexAdapter, "generate")
    assert callable(VertexAdapter.generate)


@pytest.mark.unit
def test_all_adapters_follow_base_adapter_contract():
    """Verify all adapters properly implement BaseAdapter interface."""
    from mcp_second_brain.adapters.base import BaseAdapter
    from mcp_second_brain.adapters.grok import GrokAdapter
    from mcp_second_brain.adapters.openai import OpenAIAdapter
    from mcp_second_brain.adapters.vertex import VertexAdapter

    adapters = [GrokAdapter, OpenAIAdapter, VertexAdapter]

    for adapter_class in adapters:
        # Verify it's a subclass of BaseAdapter
        assert issubclass(adapter_class, BaseAdapter)

        # Verify required attributes exist (will be set during init)
        assert hasattr(adapter_class, "generate")
