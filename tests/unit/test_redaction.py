"""Tests for secret redaction functionality."""

from mcp_second_brain.utils.redaction import redact_secrets, redact_dict


class TestRedaction:
    """Test secret redaction utilities."""

    def test_redact_api_keys(self):
        """Test redaction of API keys."""
        text = 'api_key="sk-1234567890abcdefghijklmnop"'
        assert redact_secrets(text) == "api_key=REDACTED"

        text = "APIKEY: abc123def456ghi789jkl012mno345"
        assert redact_secrets(text) == "APIKEY=REDACTED"

    def test_redact_aws_keys(self):
        """Test redaction of AWS keys."""
        text = "aws_access_key_id=AKIAIOSFODNN7EXAMPLE"
        assert redact_secrets(text) == "aws_access_key_id=AWS_ACCESS_KEY_REDACTED"

        text = 'aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"'
        assert redact_secrets(text) == "aws_secret_access_key=REDACTED"

    def test_redact_github_tokens(self):
        """Test redaction of GitHub tokens."""
        text = "token: ghp_16C7e42F292c6912E7710c838347Ae178B4a"
        assert redact_secrets(text) == "token=REDACTED"

    def test_redact_database_urls(self):
        """Test redaction of database URLs."""
        text = "postgres://myuser:mypassword@localhost:5432/mydb"
        assert redact_secrets(text) == "postgres://user:REDACTED@localhost:5432/mydb"

    def test_redact_private_keys(self):
        """Test redaction of private keys."""
        text = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA3Tz2mr7SZiAMfQyuvBjM9Oi...
-----END RSA PRIVATE KEY-----"""
        result = redact_secrets(text)
        assert "-----BEGIN PRIVATE KEY-----" in result
        assert "REDACTED" in result
        assert "MIIEowIBAAKCAQEA" not in result

    def test_redact_dict_simple(self):
        """Test redaction in simple dictionaries."""
        data = {
            "message": "My api_key: sk-1234567890abcdefghijklmnop",
            "name": "John Doe",
            "count": 42,
        }
        result = redact_dict(data)
        assert "api_key=REDACTED" in result["message"]
        assert result["name"] == "John Doe"
        assert result["count"] == 42

    def test_redact_dict_nested(self):
        """Test redaction in nested dictionaries."""
        data = {
            "config": {
                "database_url": "postgres://user:password@host/db",
                "api_settings": {"token": "ghp_16C7e42F292c6912E7710c838347Ae178B4a"},
            },
            "safe_data": "This is safe",
        }
        result = redact_dict(data)
        assert result["config"]["database_url"] == "postgres://user:REDACTED@host/db"
        assert result["config"]["api_settings"]["token"] == "GITHUB_TOKEN_REDACTED"
        assert result["safe_data"] == "This is safe"

    def test_redact_dict_with_lists(self):
        """Test redaction in dictionaries with lists."""
        data = {
            "messages": [
                {"role": "user", "content": "My api_key: sk-1234567890abcdefghijk"},
                {"role": "assistant", "content": "I'll help you"},
            ]
        }
        result = redact_dict(data)
        assert "api_key=REDACTED" in result["messages"][0]["content"]
        assert result["messages"][1]["content"] == "I'll help you"

    def test_preserve_non_secrets(self):
        """Test that non-secrets are preserved."""
        text = "This is a normal message with no secrets"
        assert redact_secrets(text) == text

        text = "token.length = 40"  # Not a token pattern
        assert redact_secrets(text) == text
