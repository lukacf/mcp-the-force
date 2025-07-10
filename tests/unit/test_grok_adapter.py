"""Unit tests for Grok adapter."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_second_brain.adapters.grok import GrokAdapter, GROK_CAPABILITIES
from mcp_second_brain.adapters.grok.errors import AdapterException, ErrorCategory


class TestGrokAdapter:
    """Test Grok adapter functionality."""

    def test_grok_capabilities(self):
        """Test that Grok models are properly defined."""
        assert "grok-3-beta" in GROK_CAPABILITIES
        assert "grok-3-fast" in GROK_CAPABILITIES
        assert "grok-4" in GROK_CAPABILITIES
        assert "grok-3-mini" in GROK_CAPABILITIES

        # Check context windows
        assert GROK_CAPABILITIES["grok-3-beta"]["context_window"] == 131_000
        assert GROK_CAPABILITIES["grok-3-fast"]["context_window"] == 131_000
        assert GROK_CAPABILITIES["grok-4"]["context_window"] == 256_000
        assert GROK_CAPABILITIES["grok-3-mini"]["context_window"] == 32_000

        # Check reasoning_effort support
        assert GROK_CAPABILITIES["grok-3-mini"]["supports_reasoning_effort"] is True
        assert (
            GROK_CAPABILITIES["grok-3-mini-beta"]["supports_reasoning_effort"] is True
        )
        assert (
            GROK_CAPABILITIES["grok-3-mini-fast"]["supports_reasoning_effort"] is True
        )

    def test_adapter_init_without_api_key(self):
        """Test adapter initialization fails without API key."""
        with patch(
            "mcp_second_brain.adapters.grok.adapter.get_settings"
        ) as mock_settings:
            mock_settings.return_value.xai.api_key = None

            with pytest.raises(AdapterException) as exc_info:
                GrokAdapter("grok-3")

            assert exc_info.value.error_category == ErrorCategory.CONFIGURATION
            assert "XAI_API_KEY not configured" in str(exc_info.value)

    def test_adapter_init_with_api_key(self):
        """Test adapter initialization succeeds with API key."""
        with patch(
            "mcp_second_brain.adapters.grok.adapter.get_settings"
        ) as mock_settings:
            mock_settings.return_value.xai.api_key = "xai-test-key"

            with patch(
                "mcp_second_brain.adapters.grok.adapter.AsyncOpenAI"
            ) as mock_client:
                adapter = GrokAdapter("grok-3-beta")

                assert adapter.model_name == "grok-3-beta"
                assert adapter.context_window == 131_000
                mock_client.assert_called_once_with(
                    api_key="xai-test-key",
                    base_url="https://api.x.ai/v1",
                )

    @pytest.mark.asyncio
    async def test_generate_with_unsupported_model(self):
        """Test generate fails with unsupported model."""
        with patch(
            "mcp_second_brain.adapters.grok.adapter.get_settings"
        ) as mock_settings:
            mock_settings.return_value.xai.api_key = "xai-test-key"

            adapter = GrokAdapter()

            with pytest.raises(AdapterException) as exc_info:
                await adapter.generate(
                    prompt="Hello",
                    model="grok-5",  # Non-existent model
                    messages=[{"role": "user", "content": "Hello"}],
                )

            assert exc_info.value.error_category == ErrorCategory.INVALID_REQUEST
            assert "Model grok-5 not supported" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful generation."""
        with patch(
            "mcp_second_brain.adapters.grok.adapter.get_settings"
        ) as mock_settings:
            mock_settings.return_value.xai.api_key = "xai-test-key"

            with patch(
                "mcp_second_brain.adapters.grok.adapter.AsyncOpenAI"
            ) as mock_client_class:
                # Create mock response
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = "Hello from Grok!"
                mock_response.choices[0].message.tool_calls = None
                mock_response.usage.prompt_tokens = 10
                mock_response.usage.completion_tokens = 5
                mock_response.usage.total_tokens = 15

                # Setup mock client
                mock_client = AsyncMock()
                mock_client.chat.completions.create = AsyncMock(
                    return_value=mock_response
                )
                mock_client_class.return_value = mock_client

                adapter = GrokAdapter()
                result = await adapter.generate(
                    prompt="Hello",
                    model="grok-3-beta",
                    messages=[{"role": "user", "content": "Hello"}],
                    temperature=0.7,
                )

                assert result == "Hello from Grok!"
                mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_streaming(self):
        """Test streaming generation."""
        with patch(
            "mcp_second_brain.adapters.grok.adapter.get_settings"
        ) as mock_settings:
            mock_settings.return_value.xai.api_key = "xai-test-key"

            with patch(
                "mcp_second_brain.adapters.grok.adapter.AsyncOpenAI"
            ) as mock_client_class:
                # Create mock streaming response
                async def mock_stream():
                    chunks = ["Hello", " from", " Grok!"]
                    for chunk_text in chunks:
                        chunk = MagicMock()
                        chunk.choices = [MagicMock()]
                        chunk.choices[0].delta.content = chunk_text
                        chunk.choices[0].delta.tool_calls = None
                        yield chunk

                # Setup mock client
                mock_client = AsyncMock()
                mock_client.chat.completions.create = AsyncMock(
                    return_value=mock_stream()
                )
                mock_client_class.return_value = mock_client

                adapter = GrokAdapter()
                result = await adapter.generate(
                    prompt="Hello",
                    model="grok-3-beta",
                    messages=[{"role": "user", "content": "Hello"}],
                    stream=True,
                )

                # Since our adapter collects streaming responses
                assert result == "Hello from Grok!"

    @pytest.mark.asyncio
    async def test_generate_handles_rate_limit(self):
        """Test rate limit error handling."""
        with patch(
            "mcp_second_brain.adapters.grok.adapter.get_settings"
        ) as mock_settings:
            mock_settings.return_value.xai.api_key = "xai-test-key"

            with patch(
                "mcp_second_brain.adapters.grok.adapter.AsyncOpenAI"
            ) as mock_client_class:
                # Setup mock client to raise rate limit error
                mock_client = AsyncMock()
                mock_client.chat.completions.create = AsyncMock(
                    side_effect=Exception("Rate limit exceeded")
                )
                mock_client_class.return_value = mock_client

                adapter = GrokAdapter()

                with pytest.raises(AdapterException) as exc_info:
                    await adapter.generate(
                        prompt="Hello",
                        model="grok-3-beta",
                        messages=[{"role": "user", "content": "Hello"}],
                    )

                assert exc_info.value.error_category == ErrorCategory.RATE_LIMIT
                assert "Rate limit exceeded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_with_reasoning_effort(self):
        """Test generation with reasoning_effort parameter for mini models."""
        with patch(
            "mcp_second_brain.adapters.grok.adapter.get_settings"
        ) as mock_settings:
            mock_settings.return_value.xai.api_key = "xai-test-key"

            with patch(
                "mcp_second_brain.adapters.grok.adapter.AsyncOpenAI"
            ) as mock_client_class:
                # Create mock response
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = "Response with reasoning"
                mock_response.choices[0].message.tool_calls = None
                mock_response.usage.prompt_tokens = 10
                mock_response.usage.completion_tokens = 5
                mock_response.usage.total_tokens = 15

                # Setup mock client
                mock_client = AsyncMock()
                mock_client.chat.completions.create = AsyncMock(
                    return_value=mock_response
                )
                mock_client_class.return_value = mock_client

                adapter = GrokAdapter()
                result = await adapter.generate(
                    prompt="Analyze this",
                    model="grok-3-mini",
                    messages=[{"role": "user", "content": "Analyze this"}],
                    reasoning_effort="high",
                )

                assert result == "Response with reasoning"

                # Verify reasoning_effort was passed
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert "reasoning_effort" in call_kwargs
                assert call_kwargs["reasoning_effort"] == "high"
