"""Tests to verify HNSW is the default vector store provider.

The OpenAI vector store should be opt-in, not the default.
HNSW (local) should be the default provider for better out-of-box experience.
"""

from unittest.mock import patch, MagicMock


class TestVectorStoreDefaultProvider:
    """Verify HNSW is the default vector store provider."""

    def test_default_provider_is_hnsw(self):
        """Default vector store provider should be 'hnsw', not 'openai'."""
        from mcp_the_force.config import MCPConfig

        # Get the default value from the model field
        field_info = MCPConfig.model_fields["default_vector_store_provider"]
        default_value = field_info.default

        assert default_value == "hnsw", (
            f"Expected default_vector_store_provider to be 'hnsw', got '{default_value}'. "
            "OpenAI vector store should be opt-in, not the default."
        )

    def test_vector_store_manager_uses_hnsw_by_default(self):
        """VectorStoreManager should use HNSW provider by default."""
        with patch("mcp_the_force.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.mcp.default_vector_store_provider = "hnsw"
            mock_settings.return_value = settings

            # Clear any cached imports
            import importlib
            import mcp_the_force.vectorstores.manager as manager_module

            importlib.reload(manager_module)

            manager = manager_module.VectorStoreManager()
            assert manager.provider == "hnsw", (
                f"Expected VectorStoreManager.provider to be 'hnsw', got '{manager.provider}'. "
                "HNSW should be the default provider."
            )

    def test_config_example_shows_hnsw_default(self):
        """config.yaml.example should show HNSW as the default."""
        from pathlib import Path

        config_example = Path(__file__).parent.parent.parent / "config.yaml.example"
        if config_example.exists():
            content = config_example.read_text()
            # Should show hnsw as default
            assert (
                "default_vector_store_provider: hnsw" in content
            ), "config.yaml.example should show 'hnsw' as the default vector store provider"


class TestVectorStoreProviderOptions:
    """Verify all provider options are still available."""

    def test_openai_provider_still_available(self):
        """OpenAI provider should still be available as opt-in."""
        from mcp_the_force.vectorstores import registry

        providers = registry.list_providers()
        assert "openai" in providers, "OpenAI provider should still be registered"

    def test_hnsw_provider_available(self):
        """HNSW provider should be available."""
        from mcp_the_force.vectorstores import registry

        providers = registry.list_providers()
        assert "hnsw" in providers, "HNSW provider should be registered"

    def test_inmemory_provider_available(self):
        """In-memory provider should be available."""
        from mcp_the_force.vectorstores import registry

        providers = registry.list_providers()
        assert "inmemory" in providers, "In-memory provider should be registered"
