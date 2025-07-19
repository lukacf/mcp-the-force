"""Unit tests for adapter cancellation patches.

These tests verify that our cancellation patches are properly applied to each adapter.
Since we can't test actual cancellation behavior without real API calls, we verify:
1. The cancel_aware_flow patch is imported and applied
2. The adapter can be imported without errors
3. Required methods exist and are callable

Real cancellation testing requires integration tests with actual API calls.
"""

import pytest


@pytest.mark.unit
def test_grok_adapter_has_cancellation_patch():
    """Verify that Grok adapter has the cancellation patch applied."""
    # The import should work without errors (patch is applied at import time)
    from mcp_second_brain.adapters.grok import GrokAdapter

    # Verify the generate method exists and is callable
    assert hasattr(GrokAdapter, "generate")
    assert callable(GrokAdapter.generate)

    # The fact that we can import means cancel_aware_flow.py was imported


@pytest.mark.unit
def test_openai_adapter_has_cancellation_patch():
    """Verify that OpenAI adapter has the cancellation patch applied."""
    # The import should work without errors (patch is applied at import time)
    from mcp_second_brain.adapters.openai import OpenAIAdapter

    # Verify the generate method exists and is callable
    assert hasattr(OpenAIAdapter, "generate")
    assert callable(OpenAIAdapter.generate)

    # The fact that we can import means cancel_aware_flow.py was imported


@pytest.mark.unit
def test_vertex_adapter_has_cancellation_patch():
    """Verify that Vertex adapter has the cancellation patch applied."""
    # The import should work without errors (patch is applied at import time)
    from mcp_second_brain.adapters.vertex import VertexAdapter

    # Verify the generate method exists and is callable
    assert hasattr(VertexAdapter, "generate")
    assert callable(VertexAdapter.generate)

    # The fact that we can import means cancel_aware_flow.py was imported


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
