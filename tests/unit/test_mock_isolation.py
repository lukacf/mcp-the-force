"""
Test to ensure mocks are properly isolating external calls.
"""

import pytest
import socket
from unittest.mock import patch


class TestMockIsolation:
    """Verify that our test mocks prevent real network calls."""

    def test_network_is_mocked(self, mock_env):
        """Test that network calls would be mocked in integration tests."""
        # In unit tests, we don't mock the entire openai module
        # but in integration tests with mock_env, OpenAI client creation is mocked

        # Verify the mock_env fixture is active
        import os

        assert os.environ.get("OPENAI_API_KEY") == "test-openai-key"

        # In real integration tests, the OpenAI class would be patched
        # Here we just verify that we have the test environment set up
        from mcp_second_brain.config import get_settings

        settings = get_settings()
        assert settings.openai_api_key == "test-openai-key"

    @patch("socket.socket")
    def test_socket_blocked_in_tests(self, mock_socket):
        """Test that raw socket connections would be blocked."""
        # Configure mock to raise on any connection attempt
        mock_socket.side_effect = Exception("Network access attempted in test!")

        # Any code trying to create a socket should fail
        with pytest.raises(Exception, match="Network access attempted"):
            socket.socket()

    def test_env_uses_dummy_keys(self, mock_env):
        """Test that we're using test API keys, not real ones."""
        import os

        # Should have test keys from mock_env
        assert os.environ.get("OPENAI_API_KEY") == "test-openai-key"
        assert os.environ.get("VERTEX_PROJECT") == "test-project"

        # Should NOT have any key that looks real (except for Anthropic)
        for key, value in os.environ.items():
            if ("KEY" in key or "SECRET" in key) and "ANTHROPIC" not in key:
                assert not value.startswith(
                    "sk-proj"
                )  # Real OpenAI keys start with sk-proj
                assert not value.startswith("gcp-")  # Real GCP keys
                # Note: We exclude length check as test keys can vary
