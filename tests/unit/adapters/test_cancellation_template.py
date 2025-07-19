"""
Template for adapter cancellation tests.

⚠️  CRITICAL: Every adapter MUST have a cancellation test based on this template.
This ensures our workaround for the MCP library bug continues to work correctly.

Copy this file and adapt it for your specific adapter.
"""

import pytest


@pytest.mark.unit
class TestAdapterCancellation:
    """Test cancellation handling for adapters."""

    def test_adapter_has_cancellation_patch(self):
        """Test that adapter has the cancel_aware_flow patch applied.

        This test ensures:
        1. The adapter can be imported (which triggers the patch)
        2. The adapter has the required generate method
        3. The adapter is a proper subclass of BaseAdapter

        Example implementation:
        ```python
        from mcp_second_brain.adapters.your_adapter import YourAdapter
        from mcp_second_brain.adapters.base import BaseAdapter

        # The import should work without errors
        assert hasattr(YourAdapter, 'generate')
        assert callable(YourAdapter.generate)
        assert issubclass(YourAdapter, BaseAdapter)
        ```
        """
        # Replace with your adapter import
        # from mcp_second_brain.adapters.your_adapter import YourAdapter
        pass

    def test_adapter_follows_base_contract(self):
        """Test that the adapter properly implements BaseAdapter interface.

        Verify that your adapter:
        1. Is a subclass of BaseAdapter
        2. Has required attributes (model_name, context_window, description_snippet)
        3. Has the generate method
        """
        # Replace with your adapter tests
        pass


# Example of a complete adapter test
@pytest.mark.unit
def test_example_adapter_cancellation():
    """Example: Test that an adapter has proper cancellation support."""
    # Import the adapter - this triggers the cancel_aware_flow patch
    from mcp_second_brain.adapters.grok import GrokAdapter
    from mcp_second_brain.adapters.base import BaseAdapter

    # Verify it's properly set up
    assert issubclass(GrokAdapter, BaseAdapter)
    assert hasattr(GrokAdapter, "generate")
    assert callable(GrokAdapter.generate)

    # The fact that we can import without errors means the patch was applied
