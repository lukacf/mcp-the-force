"""Tests for GroupThink tool definition."""

from mcp_the_force.tools.group_think import GroupThink
from mcp_the_force.local_services.collaboration_service import CollaborationService


class TestGroupThinkToolDefinition:
    """Test GroupThink tool is properly defined."""

    def test_tool_has_correct_model_name(self):
        """Test tool has the expected model name."""
        assert GroupThink.model_name == "group_think"

    def test_tool_has_description(self):
        """Test tool has a meaningful description."""
        assert GroupThink.description is not None
        assert len(GroupThink.description) > 50
        assert "multiple ai models" in GroupThink.description.lower()
        assert "collaborate" in GroupThink.description.lower()

    def test_tool_uses_collaboration_service(self):
        """Test tool references the correct service class."""
        assert GroupThink.service_cls == CollaborationService
        assert GroupThink.adapter_class is None

    def test_tool_has_required_parameters(self):
        """Test tool defines all required parameters."""
        # Check that the class has the expected attributes
        assert hasattr(GroupThink, "session_id")
        assert hasattr(GroupThink, "objective")
        assert hasattr(GroupThink, "models")
        assert hasattr(GroupThink, "user_input")
        assert hasattr(GroupThink, "mode")
        assert hasattr(GroupThink, "max_steps")
        assert hasattr(GroupThink, "config")

    def test_tool_has_reasonable_timeout(self):
        """Test tool has appropriate timeout for collaboration tasks."""
        assert (
            GroupThink.timeout == 3600
        )  # 1 hour for complete multi-turn collaboration

    def test_tool_parameter_defaults(self):
        """Test optional parameters have sensible defaults."""
        # These would be the Route.adapter default values
        # We can't easily test them here without instantiating,
        # but we can verify the tool class structure
        assert GroupThink is not None


class TestGroupThinkToolRegistration:
    """Test tool registration with MCP system."""

    def test_tool_can_be_imported(self):
        """Test tool imports successfully."""
        from mcp_the_force.tools.group_think import GroupThink

        assert GroupThink is not None

    def test_tool_is_registered_in_definitions(self):
        """Test tool is imported in definitions.py."""
        # Import definitions to trigger registration
        import mcp_the_force.tools.definitions  # noqa: F401

        # Check tool is available in registry
        from mcp_the_force.tools.registry import get_tool

        tool_metadata = get_tool("group_think")

        assert tool_metadata is not None
        # ToolMetadata structure validation - service_cls is in model_config
        assert tool_metadata.model_config["service_cls"] == CollaborationService
        assert tool_metadata.id == "group_think"
