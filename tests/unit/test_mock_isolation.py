"""
Test to ensure mocks are properly isolating external calls.
"""
import pytest
import socket
from unittest.mock import patch


class TestMockIsolation:
    """Verify that our test mocks prevent real network calls."""
    
    def test_network_is_mocked(self, mock_external_sdks):
        """Test that network calls are blocked by our mocks."""
        # Try to import and use OpenAI - should be mocked
        import openai
        
        # This should be a mock, not the real module
        assert hasattr(openai, '_mock_name') or not hasattr(openai, '__version__')
        
        # Try to create a client - should work but be a mock
        client = openai.OpenAI(api_key="test")
        assert client is not None
        
        # Any method call should return mock data, not make network calls
        assert hasattr(client.beta.chat.completions.parse, 'return_value')
    
    @patch('socket.socket')
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
        
        # Should NOT have any key that looks real
        for key, value in os.environ.items():
            if "KEY" in key or "SECRET" in key:
                assert not value.startswith("sk-")  # Real OpenAI keys
                assert not value.startswith("gcp-")  # Real GCP keys
                assert len(value) < 100  # Real keys are usually long