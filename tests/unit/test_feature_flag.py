"""Test feature flag configuration and behavior."""

import os
import tempfile
from unittest.mock import patch

from mcp_second_brain.config import get_settings


class TestFeatureFlag:
    """Test feature flag configuration."""

    def test_feature_flag_default_is_false(self):
        """Test that feature flag defaults to false."""
        # Clear any env vars that might affect this
        with patch.dict(os.environ, {}, clear=True):
            settings = get_settings()
            assert settings.features.enable_stable_inline_list is False

    def test_feature_flag_from_env_var(self):
        """Test setting feature flag via environment variable."""
        with patch.dict(os.environ, {"ENABLE_STABLE_INLINE_LIST": "true"}):
            # Clear the cached settings
            get_settings.cache_clear()
            settings = get_settings()
            assert settings.features.enable_stable_inline_list is True

        # Test with false
        with patch.dict(os.environ, {"ENABLE_STABLE_INLINE_LIST": "false"}):
            get_settings.cache_clear()
            settings = get_settings()
            assert settings.features.enable_stable_inline_list is False

    def test_feature_flag_from_nested_env_var(self):
        """Test setting feature flag via nested environment variable."""
        with patch.dict(os.environ, {"FEATURES__ENABLE_STABLE_INLINE_LIST": "true"}):
            get_settings.cache_clear()
            settings = get_settings()
            assert settings.features.enable_stable_inline_list is True

    def test_feature_flag_from_yaml(self):
        """Test setting feature flag via YAML config."""
        yaml_content = """
features:
  enable_stable_inline_list: true
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            config_file = f.name

        try:
            with patch.dict(os.environ, {"MCP_CONFIG_FILE": config_file}):
                get_settings.cache_clear()
                settings = get_settings()
                assert settings.features.enable_stable_inline_list is True
        finally:
            os.unlink(config_file)

    def test_env_var_overrides_yaml(self):
        """Test that environment variable overrides YAML config."""
        yaml_content = """
features:
  enable_stable_inline_list: false
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            config_file = f.name

        try:
            # Env var should override YAML
            with patch.dict(
                os.environ,
                {
                    "MCP_CONFIG_FILE": config_file,
                    "FEATURES__ENABLE_STABLE_INLINE_LIST": "true",
                },
            ):
                get_settings.cache_clear()
                settings = get_settings()
                assert settings.features.enable_stable_inline_list is True
        finally:
            os.unlink(config_file)
