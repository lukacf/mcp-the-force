"""Unit tests for Ollama blueprint generator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_the_force.adapters.ollama.blueprint_generator import OllamaBlueprints
from mcp_the_force.adapters.ollama.overrides import ResolvedCapabilities


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock()
    settings.ollama.enabled = True
    settings.ollama.host = "http://localhost:11434"
    settings.ollama.discover_on_startup = True
    settings.ollama.refresh_interval_sec = 0  # Disable periodic refresh for tests
    settings.ollama.context_overrides = []
    settings.ollama.memory_aware_context = False
    settings.ollama.memory_safety_margin = 0.8
    settings.ollama.default_context_window = 16384
    return settings


@pytest.fixture
def mock_models_list():
    """Mock list of models from Ollama."""
    return [
        {
            "name": "llama3:latest",
            "model": "llama3:latest",
            "size": 5368709120,
        },
        {
            "name": "mistral:7b-instruct",
            "model": "mistral:7b-instruct",
            "size": 7700000000,
        },
    ]


@pytest.fixture
def mock_model_details():
    """Mock model details."""
    return {
        "llama3:latest": {
            "context_length": 131072,
            "family": "llama",
            "parameter_size": "8B",
        },
        "mistral:7b-instruct": {
            "context_length": 32768,
            "family": "mistral",
            "parameter_size": "7B",
        },
    }


class TestOllamaBlueprints:
    """Tests for OllamaBlueprints class."""

    @pytest.mark.asyncio
    async def test_initialize_enabled(self, mock_settings):
        """Test initialization when Ollama is enabled."""
        with patch(
            "mcp_the_force.adapters.ollama.blueprint_generator.get_settings",
            return_value=mock_settings,
        ):
            generator = OllamaBlueprints()
            with patch.object(generator, "refresh", AsyncMock()) as mock_refresh:
                await generator.initialize()

                assert generator._initialized is True
                mock_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_disabled(self, mock_settings):
        """Test initialization when Ollama is disabled."""
        mock_settings.ollama.enabled = False

        with patch(
            "mcp_the_force.adapters.ollama.blueprint_generator.get_settings",
            return_value=mock_settings,
        ):
            generator = OllamaBlueprints()
            with patch.object(generator, "refresh", AsyncMock()) as mock_refresh:
                await generator.initialize()

                assert generator._initialized is False
                mock_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_with_periodic_refresh(self, mock_settings):
        """Test initialization with periodic refresh enabled."""
        mock_settings.ollama.refresh_interval_sec = 300

        with patch(
            "mcp_the_force.adapters.ollama.blueprint_generator.get_settings",
            return_value=mock_settings,
        ):
            generator = OllamaBlueprints()
            with patch.object(generator, "refresh", AsyncMock()):
                with patch("asyncio.create_task") as mock_create_task:
                    await generator.initialize()

                    mock_create_task.assert_called_once()
                    assert generator._refresh_task is not None

    @pytest.mark.asyncio
    async def test_refresh_discovers_and_registers_models(
        self, mock_settings, mock_models_list, mock_model_details
    ):
        """Test refresh discovers models and creates blueprints."""
        generator = OllamaBlueprints()

        with patch(
            "mcp_the_force.adapters.ollama.blueprint_generator.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "mcp_the_force.adapters.ollama.blueprint_generator.list_models",
                AsyncMock(return_value=mock_models_list),
            ):
                with patch(
                    "mcp_the_force.adapters.ollama.blueprint_generator.discover_model_details",
                    AsyncMock(
                        side_effect=lambda host, name: mock_model_details.get(name, {})
                    ),
                ):
                    with patch(
                        "mcp_the_force.adapters.ollama.blueprint_generator.resolve_model_capabilities",
                        AsyncMock(side_effect=self._mock_resolve_capabilities),
                    ):
                        with patch(
                            "mcp_the_force.adapters.ollama.blueprint_generator.register_blueprints"
                        ) as mock_register:
                            await generator.refresh()

                            # Check blueprints were created
                            assert len(generator._blueprints) == 2
                            assert "chat_with_llama3_latest" in generator._blueprints
                            assert (
                                "chat_with_mistral_7b_instruct" in generator._blueprints
                            )

                            # Check registration was called
                            mock_register.assert_called_once()
                            registered_bps = mock_register.call_args[0][0]
                            assert len(registered_bps) == 2

                            # Verify blueprint details
                            llama_bp = generator._blueprints["chat_with_llama3_latest"]
                            assert llama_bp.model_name == "llama3:latest"
                            assert llama_bp.context_window == 131072
                            assert llama_bp.adapter_key == "ollama"

    @pytest.mark.asyncio
    async def test_refresh_handles_discovery_errors(self, mock_settings):
        """Test refresh handles errors during discovery."""
        generator = OllamaBlueprints()

        with patch(
            "mcp_the_force.adapters.ollama.blueprint_generator.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "mcp_the_force.adapters.ollama.blueprint_generator.list_models",
                AsyncMock(side_effect=Exception("Connection failed")),
            ):
                with patch(
                    "mcp_the_force.adapters.ollama.blueprint_generator.logger"
                ) as mock_logger:
                    await generator.refresh()

                    mock_logger.error.assert_called()
                    assert "Failed to refresh" in mock_logger.error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_refresh_unregisters_removed_models(
        self, mock_settings, mock_model_details
    ):
        """Test refresh unregisters models that are no longer available."""
        generator = OllamaBlueprints()

        # Set up existing blueprints
        old_model_bp = MagicMock()
        old_model_bp.model_name = "old-model:latest"

        llama_model_bp = MagicMock()
        llama_model_bp.model_name = "llama3:latest"

        generator._blueprints = {
            "chat_with_old_model": old_model_bp,
            "chat_with_llama3_latest": llama_model_bp,
        }

        # Only llama3 is in new list
        new_models = [{"name": "llama3:latest"}]

        with patch(
            "mcp_the_force.adapters.ollama.blueprint_generator.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "mcp_the_force.adapters.ollama.blueprint_generator.list_models",
                AsyncMock(return_value=new_models),
            ):
                with patch(
                    "mcp_the_force.adapters.ollama.blueprint_generator.discover_model_details",
                    AsyncMock(return_value=mock_model_details["llama3:latest"]),
                ):
                    with patch(
                        "mcp_the_force.adapters.ollama.blueprint_generator.resolve_model_capabilities",
                        AsyncMock(side_effect=self._mock_resolve_capabilities),
                    ):
                        with patch(
                            "mcp_the_force.adapters.ollama.blueprint_generator.unregister_blueprints"
                        ) as mock_unregister:
                            with patch(
                                "mcp_the_force.adapters.ollama.blueprint_generator.register_blueprints"
                            ):
                                await generator.refresh()

                                # Check old model was unregistered
                                mock_unregister.assert_called_once_with(
                                    ["old-model:latest"]
                                )

    def test_model_to_tool_name_conversion(self):
        """Test model name to tool name conversion."""
        from mcp_the_force.tools.naming import model_to_chat_tool_name

        test_cases = [
            ("llama3:latest", "chat_with_llama3_latest"),
            ("mistral-7b-instruct:q4", "chat_with_mistral_7b_instruct_q4"),
            ("gpt-oss:120b", "chat_with_gpt_oss_120b"),
            ("model.with.dots:tag", "chat_with_model_with_dots_tag"),
        ]

        for model_name, expected_tool_name in test_cases:
            assert model_to_chat_tool_name(model_name) == expected_tool_name

    def test_get_capabilities(self, mock_settings):
        """Test getting current capabilities."""
        generator = OllamaBlueprints()

        # Set up some capabilities
        caps1 = ResolvedCapabilities(
            model_name="model1",
            max_context_window=32768,
            source="override",
            description="Model 1",
        )
        caps2 = ResolvedCapabilities(
            model_name="model2",
            max_context_window=131072,
            source="discovered",
            description="Model 2",
        )

        generator._capabilities = {
            "model1": caps1,
            "model2": caps2,
        }

        result = generator.get_capabilities()

        # Should return a copy
        assert result == generator._capabilities
        assert result is not generator._capabilities
        assert len(result) == 2

    def test_shutdown(self):
        """Test shutdown cancels refresh task."""
        generator = OllamaBlueprints()

        # Create a mock task
        mock_task = MagicMock()
        mock_task.done.return_value = False
        generator._refresh_task = mock_task

        generator.shutdown()

        mock_task.cancel.assert_called_once()
        assert generator._refresh_task is None

    def test_shutdown_no_task(self):
        """Test shutdown when no task is running."""
        generator = OllamaBlueprints()
        generator._refresh_task = None

        # Should not raise
        generator.shutdown()

    async def _mock_resolve_capabilities(
        self, name, details, overrides, memory_aware, margin
    ):
        """Helper to mock resolve_model_capabilities."""
        return ResolvedCapabilities(
            model_name=name,
            max_context_window=details.get("context_length", 8192),
            source="discovered",
            description=f"{name} ({details.get('family', 'Unknown').title()} {details.get('parameter_size', '')})",
            memory_warning=None,
        )
