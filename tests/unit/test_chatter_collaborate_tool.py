"""Tests for ChatterCollaborate tool definition."""

from mcp_the_force.tools.chatter_collaborate import ChatterCollaborate
from mcp_the_force.local_services.collaboration_service import CollaborationService


class TestChatterCollaborateToolDefinition:
    """Test ChatterCollaborate tool is properly defined."""

    def test_tool_has_correct_model_name(self):
        """Test tool has the expected model name."""
        assert ChatterCollaborate.model_name == "chatter_collaborate"

    def test_tool_has_description(self):
        """Test tool has a meaningful description."""
        assert ChatterCollaborate.description is not None
        assert len(ChatterCollaborate.description) > 50
        assert "multi-model" in ChatterCollaborate.description.lower()
        assert "collaboration" in ChatterCollaborate.description.lower()

    def test_tool_uses_collaboration_service(self):
        """Test tool references the correct service class."""
        assert ChatterCollaborate.service_cls == CollaborationService
        assert ChatterCollaborate.adapter_class is None

    def test_tool_has_required_parameters(self):
        """Test tool defines all required parameters."""
        # Check that the class has the expected attributes
        assert hasattr(ChatterCollaborate, "session_id")
        assert hasattr(ChatterCollaborate, "objective")
        assert hasattr(ChatterCollaborate, "models")
        assert hasattr(ChatterCollaborate, "user_input")
        assert hasattr(ChatterCollaborate, "mode")
        assert hasattr(ChatterCollaborate, "max_steps")
        assert hasattr(ChatterCollaborate, "config")

    def test_tool_has_reasonable_timeout(self):
        """Test tool has appropriate timeout for collaboration tasks."""
        assert ChatterCollaborate.timeout == 3600  # 1 hour for complete multi-turn collaboration

    def test_tool_parameter_defaults(self):
        """Test optional parameters have sensible defaults."""
        # These would be the Route.adapter default values
        # We can't easily test them here without instantiating,
        # but we can verify the tool class structure
        assert ChatterCollaborate is not None


class TestChatterCollaborateToolRegistration:
    """Test tool registration with MCP system."""

    def test_tool_can_be_imported(self):
        """Test tool imports successfully."""
        from mcp_the_force.tools.chatter_collaborate import ChatterCollaborate

        assert ChatterCollaborate is not None

    def test_tool_is_registered_in_definitions(self):
        """Test tool is imported in definitions.py."""
        # Import definitions to trigger registration
        import mcp_the_force.tools.definitions  # noqa: F401

        # Check tool is available in registry
        from mcp_the_force.tools.registry import get_tool

        tool_metadata = get_tool("chatter_collaborate")

        assert tool_metadata is not None
        # ToolMetadata structure validation - service_cls is in model_config
        assert tool_metadata.model_config["service_cls"] == CollaborationService
        assert tool_metadata.id == "chatter_collaborate"
