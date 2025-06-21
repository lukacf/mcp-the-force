"""Configuration specific to internal integration tests."""
import os
import pytest


@pytest.fixture(scope="session", autouse=True)
def verify_mock_adapter():
    """Verify that MockAdapter is enabled for internal tests."""
    if os.environ.get("MCP_ADAPTER_MOCK", "").lower() not in {"1", "true", "yes"}:
        pytest.fail(
            "MockAdapter not enabled! Internal tests require MCP_ADAPTER_MOCK=1. "
            "This should be set by CI or manually when running tests locally."
        )
    
    # Also verify the adapter was actually injected
    from mcp_second_brain.adapters import ADAPTER_REGISTRY
    from mcp_second_brain.adapters.mock_adapter import MockAdapter
    
    for name, adapter_class in ADAPTER_REGISTRY.items():
        if adapter_class is not MockAdapter:
            pytest.fail(
                f"Adapter '{name}' is not using MockAdapter! "
                f"Got {adapter_class} instead. "
                "This suggests MCP_ADAPTER_MOCK was set too late."
            )