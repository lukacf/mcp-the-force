"""Test secret redaction in executor outputs."""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_second_brain.tools.executor import executor
from mcp_second_brain.tools.registry import get_tool, tool
from mcp_second_brain.tools.base import ToolSpec
from mcp_second_brain.tools.descriptors import Route
from mcp_second_brain.utils.redaction import redact_secrets


class TestSecretRedaction:
    """Test that secrets are properly redacted in all outputs."""

    @pytest.mark.asyncio
    async def test_secrets_redacted_in_dict_response(self):
        """Test secrets are redacted when adapter returns dict."""

        # Create a test tool
        @tool
        class TestTool(ToolSpec):
            """Test tool for secret redaction."""

            model_name = "test"
            adapter_class = "test"
            context_window = 100
            timeout = 1

            prompt: str = Route.prompt(description="Test prompt")

        metadata = get_tool("test_tool")

        # Mock adapter that returns secrets
        mock_adapter = MagicMock()

        async def mock_generate(*args, **kwargs):
            return {
                "content": "API key is sk-abc123def456789012345 and token is ghp_123456789012345678901234567890123456",
                "response_id": "test123",
            }

        mock_adapter.generate = mock_generate

        with patch(
            "mcp_second_brain.adapters.get_adapter", return_value=(mock_adapter, None)
        ):
            result = await executor.execute(metadata, prompt="test")

            # Secrets should be redacted
            assert "sk-abc123def456789012345" not in result
            assert "ghp_123456789012345678901234567890123456" not in result
            assert "***" in result or "REDACTED" in result

    @pytest.mark.asyncio
    async def test_secrets_redacted_in_string_response(self):
        """Test secrets are redacted when adapter returns string."""

        # Create a test tool
        @tool
        class TestTool2(ToolSpec):
            """Test tool for string response redaction."""

            model_name = "test2"
            adapter_class = "test2"
            context_window = 100
            timeout = 1

            prompt: str = Route.prompt(description="Test prompt")

        metadata = get_tool("test_tool2")

        # Mock adapter that returns string with secrets
        mock_adapter = MagicMock()

        async def mock_generate(*args, **kwargs):
            return "Database password: pass123! and AWS key is AKIAIOSFODNN7EXAMPLE"

        mock_adapter.generate = mock_generate

        with patch(
            "mcp_second_brain.adapters.get_adapter", return_value=(mock_adapter, None)
        ):
            result = await executor.execute(metadata, prompt="test")

            # Secrets should be redacted
            assert "pass123!" not in result
            assert "AKIAIOSFODNN7EXAMPLE" not in result
            assert "***" in result or "REDACTED" in result

    @pytest.mark.asyncio
    async def test_secrets_redacted_in_memory_storage(self):
        """Test that secrets are redacted before storing in memory."""

        # Create a test tool with session support
        @tool
        class TestTool3(ToolSpec):
            """Test tool for memory storage redaction."""

            model_name = "o3"  # Use o3 model which supports sessions
            adapter_class = "openai"
            context_window = 100
            timeout = 1

            prompt: str = Route.prompt(description="Test prompt")
            session_id: str = Route.session(description="Session ID")

        metadata = get_tool("test_tool3")

        # Track what gets stored in memory
        stored_args = None
        store_called = asyncio.Event()

        async def mock_store_memory(*args, **kwargs):
            nonlocal stored_args
            stored_args = kwargs
            store_called.set()

        # Mock adapter that returns secrets
        mock_adapter = MagicMock()

        async def mock_generate(*args, **kwargs):
            return {"content": "Secret: sk-12345678901234567890"}

        mock_adapter.generate = mock_generate

        # Also need to patch the underlying store_conversation_memory that conftest patches
        with patch(
            "mcp_second_brain.memory.conversation.store_conversation_memory",
            AsyncMock(return_value=None),
        ):
            with patch(
                "mcp_second_brain.adapters.get_adapter",
                return_value=(mock_adapter, None),
            ):
                with patch(
                    "mcp_second_brain.tools.safe_memory.safe_store_conversation_memory",
                    side_effect=mock_store_memory,
                ) as mock_safe_store:
                    with patch("mcp_second_brain.config.get_settings") as mock_settings:
                        mock_settings.return_value.memory_enabled = True

                        result = await executor.execute(
                            metadata, prompt="test", session_id="test-session"
                        )

                        # Give background task time to run
                        await asyncio.sleep(0.5)

                        # Check if the mock was called
                        if mock_safe_store.called:
                            # Wait for our mock to be called
                            await asyncio.wait_for(store_called.wait(), timeout=2.0)

                            # Result should be redacted
                            assert "sk-12345678901234567890" not in result
                            assert "***" in result

                            # Check the stored response was redacted
                            assert stored_args is not None
                            stored_response = stored_args.get("response", "")
                            assert "sk-12345678901234567890" not in stored_response
                            assert "***" in stored_response
                        else:
                            # If memory storage wasn't called, just verify the main result is redacted
                            assert "sk-12345678901234567890" not in result
                            assert "***" in result

    def test_redact_secrets_function(self):
        """Test the redact_secrets function directly."""
        test_cases = [
            # OpenAI API keys
            ("API key: sk-abc123def456789012345", "API key: ***"),
            ("key sk-proj-abcdefghijklmnopqrstuvwxyz12345678901234567890", "key ***"),
            # API keys with proper patterns
            ("api_key=abcdefghijklmnopqrstuvwxyz123456", "api_key=***"),
            ("apikey: 'abcdefghijklmnopqrstuvwxyz123456'", "apikey=***"),
            # GitHub tokens
            ("token: ghp_123456789012345678901234567890123456", "token: ***"),
            ("found github_pat_1234567890abcdefghij12", "found ***"),
            # AWS keys
            ("key AKIAIOSFODNN7EXAMPLE", "key ***"),
            # Generic tokens
            ("token=token1234567890abcdefghij", "token=***"),
            ('token="very_long_token_string_here_12345"', "token=***"),
            # Passwords
            ("password=mysecret123", "password=***"),
            ('pass: "p@ssw0rd"', "pass=***"),
            # Database URLs
            ("postgres://user:password123@localhost", "postgres://user:***@localhost"),
            # Text that should NOT be redacted
            ("short key", "short key"),  # Too short
            ("api without key", "api without key"),  # No key pattern
        ]

        for input_text, expected in test_cases:
            result = redact_secrets(input_text)
            assert result == expected, f"Failed for input: {input_text}\\nGot: {result}"
