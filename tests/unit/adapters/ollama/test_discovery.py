"""Unit tests for Ollama discovery module."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from mcp_the_force.adapters.ollama.discovery import (
    list_models,
    discover_model_details,
    calculate_viable_context,
)


class TestListModels:
    """Tests for list_models function."""

    @pytest.mark.asyncio
    async def test_list_models_success(self):
        """Test successful model listing."""
        mock_response = MagicMock()
        mock_response.json = MagicMock(
            return_value={
                "models": [
                    {
                        "name": "llama3:latest",
                        "model": "llama3:latest",
                        "modified_at": "2024-01-01T00:00:00Z",
                        "size": 5368709120,
                        "digest": "abc123",
                        "details": {
                            "format": "gguf",
                            "family": "llama",
                            "families": ["llama"],
                            "parameter_size": "8B",
                            "quantization_level": "Q4_0",
                        },
                    },
                    {
                        "name": "gpt-oss:120b",
                        "model": "gpt-oss:120b",
                        "modified_at": "2024-01-02T00:00:00Z",
                        "size": 128849018880,
                        "digest": "def456",
                    },
                ]
            }
        )
        mock_response.raise_for_status = MagicMock()

        with patch(
            "mcp_the_force.adapters.ollama.discovery.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response

            models = await list_models("http://localhost:11434")

            assert len(models) == 2
            assert models[0]["name"] == "llama3:latest"
            assert models[1]["name"] == "gpt-oss:120b"
            mock_client.get.assert_called_once_with("http://localhost:11434/api/tags")

    @pytest.mark.asyncio
    async def test_list_models_connection_error(self):
        """Test handling of connection errors."""
        with patch(
            "mcp_the_force.adapters.ollama.discovery.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.ConnectError("Connection failed")

            models = await list_models("http://localhost:11434")

            assert models == []

    @pytest.mark.asyncio
    async def test_list_models_invalid_json(self):
        """Test handling of invalid JSON response."""
        mock_response = MagicMock()
        mock_response.json = MagicMock(
            side_effect=json.JSONDecodeError("Invalid", "", 0)
        )
        mock_response.raise_for_status = MagicMock()

        with patch(
            "mcp_the_force.adapters.ollama.discovery.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response

            models = await list_models("http://localhost:11434")

            assert models == []


class TestDiscoverModelDetails:
    """Tests for discover_model_details function."""

    @pytest.mark.asyncio
    async def test_discover_model_details_with_context_length(self):
        """Test discovering model with context_length in model_info."""
        mock_response = MagicMock()
        mock_response.json = MagicMock(
            return_value={
                "license": "MIT",
                "modelfile": "FROM llama3",
                "parameters": "parameter_size 8B",
                "template": "{{ .System }} {{ .Prompt }}",
                "details": {
                    "format": "gguf",
                    "family": "llama",
                    "families": ["llama"],
                    "parameter_size": "8B",
                },
                "model_info": {
                    "llama.context_length": 131072,
                    "llama.embedding_length": 4096,
                    "llama.rope.dimension_count": 128,
                },
            }
        )
        mock_response.raise_for_status = MagicMock()

        with patch(
            "mcp_the_force.adapters.ollama.discovery.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            details = await discover_model_details(
                "http://localhost:11434", "llama3:latest"
            )

            assert details["context_window"] == 131072
            assert details["parameter_size"] == "8B"
            assert details["name"] == "llama3:latest"

    @pytest.mark.asyncio
    async def test_discover_model_details_no_context_length(self):
        """Test discovering model without context_length."""
        mock_response = MagicMock()
        mock_response.json = MagicMock(
            return_value={
                "details": {
                    "format": "gguf",
                    "family": "mistral",
                    "parameter_size": "7B",
                },
                "model_info": {
                    "general.architecture": "mistral",
                },
            }
        )
        mock_response.raise_for_status = MagicMock()

        with patch(
            "mcp_the_force.adapters.ollama.discovery.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            details = await discover_model_details(
                "http://localhost:11434", "mistral:latest"
            )

            assert details["context_window"] == 16384  # Config default when not found
            assert details["parameter_size"] == "7B"

    @pytest.mark.asyncio
    async def test_discover_model_details_connection_error(self):
        """Test handling of connection errors during discovery."""
        with patch(
            "mcp_the_force.adapters.ollama.discovery.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = httpx.ConnectError("Connection failed")

            details = await discover_model_details(
                "http://localhost:11434", "model:tag"
            )

            # Should return default structure on error
            assert details["name"] == "model:tag"
            assert details["context_window"] == 16384  # Config default
            assert details["model_info"] == {}
            assert details["parameter_size"] == "unknown"
            assert details["quantization"] == "unknown"


class TestCalculateViableContext:
    """Tests for calculate_viable_context function."""

    @pytest.mark.asyncio
    async def test_calculate_viable_context_standard_sizes(self):
        """Test context calculation returns standard sizes."""
        # Mock psutil for memory info
        mock_virtual = MagicMock()
        mock_virtual.available = 32 * 1024 * 1024 * 1024  # 32GB available

        with patch("psutil.virtual_memory", return_value=mock_virtual):
            # The function doesn't use model_memory_gb parameter in current implementation
            # It only looks at available system memory
            # 32GB available - 20GB reserved = 12GB
            # With margin: 12GB * 0.8 = 9.6GB
            # 9.6GB / 0.55 per 1K = 17.45K context -> rounds to 16384
            context = await calculate_viable_context(8.0, 0.8)
            assert context == 16384

            # Same calculation regardless of model size in current implementation
            context = await calculate_viable_context(4.0, 0.8)
            assert context == 16384

            context = await calculate_viable_context(25.0, 0.8)
            assert context == 16384

    @pytest.mark.asyncio
    async def test_calculate_viable_context_insufficient_memory(self):
        """Test context calculation with insufficient memory."""
        mock_virtual = MagicMock()
        mock_virtual.available = 8 * 1024 * 1024 * 1024  # Only 8GB available

        with patch("psutil.virtual_memory", return_value=mock_virtual):
            # 8GB available - 20GB reserved = negative, so minimum
            context = await calculate_viable_context(6.0, 0.8)
            assert context == 4096  # Minimum context

            context = await calculate_viable_context(7.5, 0.8)
            assert context == 4096  # Minimum context

    @pytest.mark.asyncio
    async def test_calculate_viable_context_custom_margin(self):
        """Test context calculation with custom safety margins."""
        mock_virtual = MagicMock()
        mock_virtual.available = 16 * 1024 * 1024 * 1024  # 16GB available

        with patch("psutil.virtual_memory", return_value=mock_virtual):
            # 16GB available - 20GB reserved = negative, so minimum
            context = await calculate_viable_context(8.0, 0.5)
            assert context == 4096

            context = await calculate_viable_context(8.0, 0.9)
            assert context == 4096

    @pytest.mark.asyncio
    async def test_calculate_viable_context_boundary_conditions(self):
        """Test boundary conditions for context calculation."""
        mock_virtual = MagicMock()

        with patch("psutil.virtual_memory", return_value=mock_virtual):
            # Test with more memory available
            mock_virtual.available = 40 * 1024 * 1024 * 1024  # 40GB
            # 40GB - 20GB reserved = 20GB
            # 20GB * 0.8 = 16GB
            # 16GB / 0.55 = 29K context -> rounds to 16384
            context = await calculate_viable_context(1.0, 0.8)
            assert context == 16384

            # Much more memory
            mock_virtual.available = 80 * 1024 * 1024 * 1024  # 80GB
            # 80GB - 20GB = 60GB * 0.8 = 48GB
            # 48GB / 0.55 = 87K context -> rounds to 65536
            context = await calculate_viable_context(1.0, 0.8)
            assert context == 65536
