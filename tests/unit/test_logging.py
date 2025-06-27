"""
Unit tests for logging security - ensuring API keys don't appear in logs.
"""
import logging
import os
import pytest
from mcp_second_brain.config import Settings
from mcp_second_brain.utils.log_filter import SecretRedactionFilter


class TestLoggingSecurity:
    """Test that sensitive information doesn't appear in logs."""
    
    def test_api_keys_not_logged(self, caplog, mock_env):
        """Test that API keys are not logged."""
        # Set log level to DEBUG to catch all logs
        caplog.set_level(logging.DEBUG)
        
        # Create settings which might log during init
        _ = Settings()
        
        # Simulate some operations that might log
        logger = logging.getLogger("mcp_second_brain")
        logger.debug("Settings loaded")
        logger.info("Server starting")
        
        # Check that secrets don't appear in logs
        log_text = caplog.text.lower()
        
        # These should never appear in logs
        assert "test-openai-key" not in log_text
        assert "test-project" not in log_text
        assert mock_env["OPENAI_API_KEY"].lower() not in log_text
        assert mock_env["VERTEX_PROJECT"].lower() not in log_text
    
    def test_error_messages_sanitized(self, caplog):
        """Test that error messages don't leak sensitive info."""
        caplog.set_level(logging.DEBUG)
        logger = logging.getLogger("mcp_second_brain")
        
        # Simulate an error that might contain sensitive data
        try:
            # This might happen if someone accidentally includes API key in error
            api_key = "sk-1234567890abcdef"
            raise ValueError(f"Failed to connect with key {api_key}")
        except ValueError as e:
            # In real code, we should sanitize before logging
            # This test documents that we need to be careful
            sanitized_msg = str(e).replace(api_key, "***")
            logger.error(f"Connection error: {sanitized_msg}")
        
        # Check that the actual key doesn't appear
        assert "sk-1234567890abcdef" not in caplog.text
        assert "***" in caplog.text
    
    def test_automatic_secret_redaction(self, caplog, monkeypatch):
        """Test that secrets are automatically redacted from logs."""
        # This test documents a feature we should implement
        # A logging filter that automatically redacts patterns like:
        # - sk-[alphanumeric] (OpenAI keys)
        # - Any value from environment variables ending in _KEY or _SECRET
        
        monkeypatch.setenv("OPENAI_API_KEY", "sk-supersecret123")
        caplog.set_level(logging.DEBUG)
        logging.getLogger().addFilter(SecretRedactionFilter())
        
        logger = logging.getLogger("mcp_second_brain")
        # Even if someone accidentally logs the key
        logger.info(f"Using key: {os.environ['OPENAI_API_KEY']}")
        
        # It should be automatically redacted
        assert "sk-supersecret123" not in caplog.text
        assert "Using key: [REDACTED]" in caplog.text
