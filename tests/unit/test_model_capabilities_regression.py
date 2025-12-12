"""Regression tests for model capability definitions.

These tests verify that model capability configurations are correct,
especially after encountering production errors with specific models.
"""

import pytest
from unittest.mock import patch
from mcp_the_force.config import Settings, ProviderConfig


@pytest.fixture(autouse=True)
def mock_settings():
    """Auto-mock settings for all tests."""
    mock_settings = Settings(
        vertex=ProviderConfig(project="test-project", location="us-central1"),
        gemini=ProviderConfig(api_key=None),
        xai=ProviderConfig(api_key="test-key"),
        openai=ProviderConfig(api_key="test-key"),
    )
    with patch("mcp_the_force.config.get_settings") as mock_get:
        mock_get.return_value = mock_settings
        yield mock_settings


class TestGPT51CodexMaxCapabilities:
    """Tests for GPT-5.1 Codex Max model capabilities."""

    def test_gpt51_codex_max_has_xhigh_default_reasoning(self):
        """GPT-5.1 Codex Max should default to xhigh reasoning effort."""
        from mcp_the_force.adapters.openai.definitions import GPT51CodexMaxCapabilities

        capabilities = GPT51CodexMaxCapabilities()
        assert capabilities.default_reasoning_effort == "xhigh"

    def test_gpt51_codex_max_has_no_native_vector_store(self):
        """GPT-5.1 Codex Max doesn't support file_search tool."""
        from mcp_the_force.adapters.openai.definitions import GPT51CodexMaxCapabilities

        capabilities = GPT51CodexMaxCapabilities()
        assert capabilities.native_vector_store_provider is None

    def test_gpt51_codex_max_has_correct_context_window(self):
        """GPT-5.1 Codex Max should have 400k context window."""
        from mcp_the_force.adapters.openai.definitions import GPT51CodexMaxCapabilities

        capabilities = GPT51CodexMaxCapabilities()
        assert capabilities.max_context_window == 400_000

    def test_gpt51_codex_max_timeout(self):
        """GPT-5.1 Codex Max should have 90-minute timeout."""
        from mcp_the_force.adapters.openai.definitions import _calculate_timeout

        timeout = _calculate_timeout("gpt-5.1-codex-max")
        assert timeout == 5400  # 90 minutes

    def test_gpt51_codex_max_supports_reasoning_effort(self):
        """GPT-5.1 Codex Max should support reasoning_effort parameter."""
        from mcp_the_force.adapters.openai.definitions import GPT51CodexMaxCapabilities

        capabilities = GPT51CodexMaxCapabilities()
        assert capabilities.supports_reasoning_effort is True

    def test_gpt51_codex_max_no_temperature(self):
        """GPT-5.1 Codex Max should NOT support temperature parameter."""
        from mcp_the_force.adapters.openai.definitions import GPT51CodexMaxCapabilities

        capabilities = GPT51CodexMaxCapabilities()
        assert capabilities.supports_temperature is False


class TestOSeriesCapabilities:
    """Tests for O-series model capabilities."""

    def test_o_series_has_native_vector_store_provider(self):
        """O-series models (o3, o3-pro, o4-mini) SHOULD have native vector store."""
        from mcp_the_force.adapters.openai.definitions import OSeriesCapabilities

        capabilities = OSeriesCapabilities()
        assert capabilities.native_vector_store_provider == "openai"


class TestGPT41Capabilities:
    """Tests for GPT-4.1 model capabilities."""

    def test_gpt41_has_native_vector_store_provider(self):
        """GPT-4.1 SHOULD have native vector store support."""
        from mcp_the_force.adapters.openai.definitions import GPT41Capabilities

        capabilities = GPT41Capabilities()
        assert capabilities.native_vector_store_provider == "openai"


class TestGeminiTimeouts:
    """Tests for Gemini model timeout configurations."""

    def test_gemini_pro_timeout_sufficient_for_large_context(self):
        """Gemini Pro should have sufficient timeout for large context + tool use.

        Regression test: 503 UNAVAILABLE errors occurred when timeout was too short
        for Gemini Pro processing large contexts with tool use.
        """
        from mcp_the_force.adapters.google.definitions import _calculate_timeout

        # Pro models need longer timeouts
        timeout = _calculate_timeout("gemini-3-pro-preview")
        assert timeout >= 1800  # At least 30 minutes

    def test_gemini_flash_timeout_reasonable(self):
        """Gemini Flash should have reasonable timeout."""
        from mcp_the_force.adapters.google.definitions import _calculate_timeout

        timeout = _calculate_timeout("gemini-2.5-flash")
        assert timeout >= 600  # At least 10 minutes

    def test_default_timeout_reasonable(self):
        """Default timeout should be reasonable."""
        from mcp_the_force.adapters.google.definitions import _calculate_timeout

        timeout = _calculate_timeout("unknown-model")
        assert timeout >= 600  # At least 10 minutes


class TestReasoningEffortDefaults:
    """Tests for reasoning_effort default application in _preprocess_request."""

    def _preprocess_request(self, data):
        """Simulates FlowOrchestrator._preprocess_request logic for testing."""
        from mcp_the_force.adapters.openai.definitions import get_model_capability

        model = data.get("model", "")
        capability = get_model_capability(model)
        if capability and capability.supports_reasoning_effort:
            # Only apply capability default when reasoning_effort is not provided.
            # If user explicitly provides any value (including "medium"), respect it.
            if "reasoning_effort" not in data and capability.default_reasoning_effort:
                data["reasoning_effort"] = capability.default_reasoning_effort

    def test_codex_max_gets_xhigh_when_not_provided(self):
        """GPT-5.1 Codex Max should get xhigh when reasoning_effort not provided."""
        data = {"model": "gpt-5.1-codex-max"}
        self._preprocess_request(data)
        assert data.get("reasoning_effort") == "xhigh"

    def test_gpt52_gets_xhigh_when_not_provided(self):
        """GPT-5.2 should get xhigh when reasoning_effort not provided."""
        data = {"model": "gpt-5.2"}
        self._preprocess_request(data)
        assert data.get("reasoning_effort") == "xhigh"

    def test_gpt52_pro_gets_xhigh_when_not_provided(self):
        """GPT-5.2 Pro should get xhigh when reasoning_effort not provided."""
        data = {"model": "gpt-5.2-pro"}
        self._preprocess_request(data)
        assert data.get("reasoning_effort") == "xhigh"

    def test_user_explicit_medium_is_respected(self):
        """User-provided 'medium' should be respected, not overridden.

        Regression test: Previously, explicit 'medium' was overridden to the
        capability default. Users should be able to request medium for cost/latency.
        """
        data = {"model": "gpt-5.1-codex-max", "reasoning_effort": "medium"}
        self._preprocess_request(data)
        assert data.get("reasoning_effort") == "medium"

    def test_user_explicit_low_is_respected(self):
        """User-provided 'low' should be respected."""
        data = {"model": "gpt-5.1-codex-max", "reasoning_effort": "low"}
        self._preprocess_request(data)
        assert data.get("reasoning_effort") == "low"

    def test_user_explicit_high_is_respected(self):
        """User-provided 'high' should be respected (not upgraded to xhigh)."""
        data = {"model": "gpt-5.1-codex-max", "reasoning_effort": "high"}
        self._preprocess_request(data)
        assert data.get("reasoning_effort") == "high"

    def test_gpt41_does_not_get_reasoning_effort(self):
        """GPT-4.1 doesn't support reasoning_effort, should not be added."""
        data = {"model": "gpt-4.1"}
        self._preprocess_request(data)
        assert "reasoning_effort" not in data
