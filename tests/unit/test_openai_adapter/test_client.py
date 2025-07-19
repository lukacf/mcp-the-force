"""Unit tests for OpenAI client factory."""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from mcp_second_brain.adapters.openai.client import OpenAIClientFactory


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_instance_returns_same_for_same_loop():
    """Verify that the same event loop gets the same client instance."""
    # Clean up any existing instances
    await OpenAIClientFactory.close_all()

    # Mock the OpenAI client to avoid actual API calls
    with patch("mcp_second_brain.adapters.openai.client.AsyncOpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Get instance twice in the same loop
        client1 = await OpenAIClientFactory.get_instance(api_key="test-key")
        client2 = await OpenAIClientFactory.get_instance(api_key="test-key")

        # Should be the same object
        assert client1 is client2

        # OpenAI constructor should only be called once
        assert mock_openai.call_count == 1

    # Clean up
    await OpenAIClientFactory.close_all()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_different_loops_get_different_instances():
    """Verify that different event loops get different client instances."""
    # Clean up any existing instances
    await OpenAIClientFactory.close_all()

    with patch("mcp_second_brain.adapters.openai.client.AsyncOpenAI") as mock_openai:
        # Create distinct mock clients
        mock_client1 = MagicMock(name="client1")
        mock_client2 = MagicMock(name="client2")
        mock_openai.side_effect = [mock_client1, mock_client2]

        # Get instance in current loop
        client1 = await OpenAIClientFactory.get_instance(api_key="test-key")

        # Get instance in a new event loop
        async def get_client_in_new_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return await OpenAIClientFactory.get_instance(api_key="test-key")
            finally:
                loop.close()

        # Run in a separate thread to ensure a completely different loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, get_client_in_new_loop())
            client2 = future.result()

        # Should be different objects
        assert client1 is not client2
        assert client1 is mock_client1
        assert client2 is mock_client2

        # OpenAI constructor should be called twice
        assert mock_openai.call_count == 2

    # Clean up
    await OpenAIClientFactory.close_all()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_client_configuration():
    """Verify that the client is configured with correct parameters."""
    # Clean up any existing instances
    await OpenAIClientFactory.close_all()

    with patch("mcp_second_brain.adapters.openai.client.AsyncOpenAI") as mock_openai:
        with patch(
            "mcp_second_brain.adapters.openai.client.httpx.AsyncClient"
        ) as mock_http_client:
            await OpenAIClientFactory.get_instance(api_key="test-key")

            # Check that httpx client was created with correct parameters
            mock_http_client.assert_called_once()
            call_kwargs = mock_http_client.call_args.kwargs

            # Verify limits
            assert call_kwargs["limits"].max_keepalive_connections == 20
            assert call_kwargs["limits"].max_connections == 100

            # Verify timeout - updated with new values to prevent stale connection hangs
            assert call_kwargs["timeout"].connect == 20.0
            assert call_kwargs["timeout"].write == 60.0
            assert call_kwargs["timeout"].read == 180.0
            assert call_kwargs["timeout"].pool == 60.0

            # Verify OpenAI client configuration
            openai_kwargs = mock_openai.call_args.kwargs
            assert openai_kwargs["api_key"] == "test-key"
            assert openai_kwargs["max_retries"] == 3
            assert "http_client" in openai_kwargs

    # Clean up
    await OpenAIClientFactory.close_all()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_access_same_loop():
    """Verify thread-safe access within the same event loop."""
    # Clean up any existing instances
    await OpenAIClientFactory.close_all()

    with patch("mcp_second_brain.adapters.openai.client.AsyncOpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Simulate concurrent access
        async def get_client():
            return await OpenAIClientFactory.get_instance(api_key="test-key")

        # Run multiple concurrent requests
        clients = await asyncio.gather(*[get_client() for _ in range(10)])

        # All should be the same instance
        assert all(c is clients[0] for c in clients)

        # Constructor should only be called once despite concurrent access
        assert mock_openai.call_count == 1

    # Clean up
    await OpenAIClientFactory.close_all()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_all():
    """Verify that close_all properly cleans up instances."""
    # Clean up any existing instances
    await OpenAIClientFactory.close_all()

    with patch("mcp_second_brain.adapters.openai.client.AsyncOpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_http_client = MagicMock()
        mock_http_client.aclose = MagicMock(return_value=asyncio.Future())
        mock_http_client.aclose.return_value.set_result(None)
        mock_client._client = mock_http_client
        mock_openai.return_value = mock_client

        # Create an instance
        await OpenAIClientFactory.get_instance(api_key="test-key")

        # Verify instance exists
        loop = asyncio.get_running_loop()
        assert loop in OpenAIClientFactory._instances

        # Close all instances
        await OpenAIClientFactory.close_all()

        # Verify cleanup
        assert len(OpenAIClientFactory._instances) == 0
        mock_http_client.aclose.assert_called_once()
