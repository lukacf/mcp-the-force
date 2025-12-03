import os
import pytest
from unittest.mock import patch, MagicMock

from mcp_the_force.adapters.google.adapter import GeminiAdapter
from mcp_the_force.adapters.errors import ConfigurationException
from mcp_the_force.config import Settings, ProviderConfig, get_settings


# Clear the lru_cache for get_settings before each test
@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()


@pytest.fixture
def mock_settings():
    """Fixture to mock the get_settings() function."""
    with patch("mcp_the_force.adapters.google.adapter.get_settings") as mock:
        settings = Settings()
        mock.return_value = settings
        yield settings


class TestGeminiAuthScenarios:
    def test_api_key_always_takes_precedence(self, mock_settings, tmp_path, caplog):
        """
        Tests that Gemini API key ALWAYS takes precedence over Vertex AI,
        even when service account credentials are configured.
        """
        # Setup: Create a dummy ADC file
        adc_file = tmp_path / "adc.json"
        adc_file.write_text("{}")

        # Configure multiple auth methods - API key should ALWAYS win
        mock_settings.vertex = ProviderConfig(
            adc_credentials_path=str(adc_file),
            project="test-project",
            location="us-central1",
        )
        mock_settings.gemini = ProviderConfig(api_key="gemini-api-key")

        # Initialize adapter
        adapter = GeminiAdapter()

        # Assertions - API key should win
        assert adapter._auth_method == "api_key"
        assert adapter._get_model_prefix() == "gemini"

        params = adapter._build_request_params([], MagicMock(), [])
        assert "api_key" in params
        assert "vertex_project" not in params

    def test_service_account_used_without_api_key(self, mock_settings, tmp_path):
        """
        Tests that service account credentials are used when API key is not set.
        """
        # Setup: Create a dummy ADC file
        adc_file = tmp_path / "adc.json"
        adc_file.write_text("{}")

        # Configure only Vertex AI (no API key)
        mock_settings.vertex = ProviderConfig(
            adc_credentials_path=str(adc_file),
            project="test-project",
            location="us-central1",
        )
        mock_settings.gemini = ProviderConfig(api_key=None)

        # Initialize adapter
        adapter = GeminiAdapter()

        # Assertions
        assert adapter._auth_method == "service_account"
        assert adapter._get_model_prefix() == "vertex_ai"

        params = adapter._build_request_params([], MagicMock(), [])
        assert "vertex_project" in params
        assert "api_key" not in params

    def test_api_key_with_vertex_config_logs_debug(self, mock_settings, caplog):
        """
        Tests that having both API key and Vertex config logs a debug message.
        """
        import logging

        caplog.set_level(logging.DEBUG)

        # Configure API key and Vertex settings
        mock_settings.gemini = ProviderConfig(api_key="gemini-api-key")
        mock_settings.vertex = ProviderConfig(
            project="test-project", location="us-central1"
        )

        adapter = GeminiAdapter()

        assert adapter._auth_method == "api_key"
        assert adapter._get_model_prefix() == "gemini"
        assert "Using Gemini API key (preferred)" in caplog.text

        params = adapter._build_request_params([], MagicMock(), [])
        assert "api_key" in params
        assert "vertex_project" not in params

    def test_implicit_adc_auth(self, mock_settings):
        """
        Tests implicit ADC auth via GOOGLE_APPLICATION_CREDENTIALS env var.
        """
        mock_settings.vertex = ProviderConfig(
            project="test-project", location="us-central1"
        )
        # Explicitly clear gemini API key to test ADC path
        mock_settings.gemini = ProviderConfig(api_key=None)

        with patch.dict(
            os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "/fake/path.json"}
        ):
            adapter = GeminiAdapter()

        assert adapter._auth_method == "implicit_adc"
        assert adapter._get_model_prefix() == "vertex_ai"

    def test_fallback_adc_auth(self, mock_settings):
        """
        Tests fallback ADC auth when only project and location are set.
        """
        mock_settings.vertex = ProviderConfig(
            project="test-project", location="us-central1"
        )
        # Explicitly clear gemini API key to test ADC path
        mock_settings.gemini = ProviderConfig(api_key=None)

        adapter = GeminiAdapter()

        assert adapter._auth_method == "fallback_adc"
        assert adapter._get_model_prefix() == "vertex_ai"

    def test_no_credentials_raises_exception(self, mock_settings):
        """
        Tests that a ConfigurationException is raised if no credentials are provided.
        """
        mock_settings.vertex = ProviderConfig(project=None, location=None)
        mock_settings.gemini = ProviderConfig(api_key=None)

        with pytest.raises(ConfigurationException) as excinfo:
            GeminiAdapter()

        assert "No valid Gemini/Vertex AI credentials found" in str(excinfo.value)


class TestAdcPathHandling:
    def test_init_with_nonexistent_adc_path_logs_warning(self, tmp_path, caplog):
        """
        Tests that Settings.__init__ logs a warning but doesn't crash for a missing ADC file.
        """
        config_dir = tmp_path
        adc_path = config_dir / ".gcp" / "adc.json"  # Path does not exist

        with patch.dict(
            os.environ, {"MCP_CONFIG_FILE": str(config_dir / "config.yaml")}
        ):
            Settings(vertex=ProviderConfig(adc_credentials_path=str(adc_path)))

        assert f"ADC credentials file not found at {adc_path}" in caplog.text
        assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ

    def test_init_with_existing_adc_path_sets_env_var(self, tmp_path):
        """
        Tests that Settings.__init__ sets the environment variable for an existing ADC file.
        """
        # Setup
        config_dir = tmp_path
        gcp_dir = config_dir / ".gcp"
        gcp_dir.mkdir()
        adc_file = gcp_dir / "adc.json"
        adc_file.write_text("{}")

        # Clean up environment variable if it exists
        if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
            del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

        with patch.dict(
            os.environ, {"MCP_CONFIG_FILE": str(config_dir / "config.yaml")}
        ):
            Settings(vertex=ProviderConfig(adc_credentials_path=str(adc_file)))
            assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(adc_file)

        # The patch.dict context manager handles cleanup automatically.
        # No need to manually delete the environment variable.
