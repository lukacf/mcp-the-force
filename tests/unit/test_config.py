"""
Unit tests for configuration and settings.
"""
import os
import pytest
from unittest.mock import patch
from mcp_second_brain.config import Settings


class TestSettings:
    """Test Settings configuration."""
    
    def test_default_settings(self):
        """Test that default settings are loaded."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            
            # Check defaults
            assert settings.host == "127.0.0.1"
            assert settings.port == 8000
            assert settings.max_inline_tokens is None  # None by default
            assert settings.default_temperature == 0.2
    
    def test_env_var_override(self, mock_env):
        """Test that environment variables override defaults."""
        # mock_env fixture sets test values
        settings = Settings()
        
        assert settings.openai_api_key == "test-openai-key"
        assert settings.vertex_project == "test-project"
        assert settings.vertex_location == "us-central1"
        assert settings.max_inline_tokens == 12000  # From mock_env
    
    def test_custom_env_values(self):
        """Test custom environment values."""
        custom_env = {
            "HOST": "0.0.0.0",
            "PORT": "9000",
            "MAX_INLINE_TOKENS": "24000",
            "DEFAULT_TEMPERATURE": "0.7"
        }
        
        with patch.dict(os.environ, custom_env, clear=True):
            settings = Settings()
            
            assert settings.host == "0.0.0.0"
            assert settings.port == 9000
            assert settings.max_inline_tokens == 24000
            assert settings.default_temperature == 0.7
    
    def test_invalid_port(self):
        """Test that invalid port raises error."""
        with patch.dict(os.environ, {"PORT": "not-a-number"}, clear=True):
            with pytest.raises(ValueError):
                Settings()
    
    def test_temperature_accepts_any_float(self):
        """Test that temperature accepts any float value (no validation)."""
        with patch.dict(os.environ, {"DEFAULT_TEMPERATURE": "2.5"}, clear=True):
            settings = Settings()
            assert settings.default_temperature == 2.5
    
    def test_missing_api_keys_allowed(self):
        """Test that missing API keys don't prevent initialization."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            
            # Should be empty strings, not raise
            assert settings.openai_api_key == ""
            assert settings.vertex_project == ""
    
    def test_dotenv_loading(self, tmp_path, monkeypatch):
        """Test that .env file is loaded."""
        # Create a .env file
        env_file = tmp_path / ".env"
        env_file.write_text("""
OPENAI_API_KEY=from-dotenv
HOST=192.168.1.1
PORT=3000
""")
        
        # Change to temp directory
        monkeypatch.chdir(tmp_path)
        
        # Clear environment first
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            
            # Should load from .env
            assert settings.openai_api_key == "from-dotenv"
            assert settings.host == "192.168.1.1"
            assert settings.port == 3000
    
    def test_env_precedence_over_dotenv(self, tmp_path, monkeypatch):
        """Test that environment variables take precedence over .env file."""
        # Create a .env file
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=from-dotenv")
        
        monkeypatch.chdir(tmp_path)
        
        # Set environment variable
        with patch.dict(os.environ, {"OPENAI_API_KEY": "from-env"}, clear=True):
            settings = Settings()
            
            # Environment should win
            assert settings.openai_api_key == "from-env"
    
    def test_case_insensitivity(self):
        """Test that pydantic-settings is case-insensitive by default."""
        with patch.dict(os.environ, {"openai_api_key": "lowercase"}, clear=True):
            settings = Settings()
            
            # pydantic-settings is case-insensitive, so it should pick up the value
            assert settings.openai_api_key == "lowercase"
    
    def test_vertex_endpoint_property(self):
        """Test that vertex_endpoint property is computed correctly."""
        with patch.dict(os.environ, {
            "VERTEX_PROJECT": "my-project",
            "VERTEX_LOCATION": "europe-west1"
        }, clear=True):
            settings = Settings()
            
            assert settings.vertex_endpoint == "projects/my-project/locations/europe-west1"
    
    def test_get_settings_cached(self):
        """Test that get_settings() returns cached instance."""
        from mcp_second_brain.config import get_settings
        
        # Clear cache first
        get_settings.cache_clear()
        
        # Get settings twice
        settings1 = get_settings()
        settings2 = get_settings()
        
        # Should be the same instance
        assert settings1 is settings2