"""Unit tests for structured output parameter routing."""

from typing import Dict, Any
from mcp_the_force.tools.parameter_router import ParameterRouter
from mcp_the_force.tools.registry import ToolMetadata, ParameterInfo, tool
from mcp_the_force.tools.descriptors import Route, RouteType, RouteDescriptor
from mcp_the_force.tools.base import ToolSpec


class TestStructuredOutputRouting:
    """Test that structured_output_schema parameter routes correctly."""

    def test_route_descriptor_exists(self):
        """Test that Route.structured_output() descriptor exists."""
        # This should not raise AttributeError when implemented
        descriptor = Route.structured_output(description="Test schema")
        assert isinstance(descriptor, RouteDescriptor)
        assert descriptor.route == RouteType.STRUCTURED_OUTPUT
        assert descriptor.description == "Test schema"

    def test_structured_output_routes_to_adapter(self):
        """Test that structured_output_schema routes to adapter params."""

        # Create a test tool with structured output
        @tool
        class TestTool(ToolSpec):
            model_name = "gpt-4.1"
            adapter_class = "openai"

            instructions: str = Route.prompt()
            structured_output_schema: Dict[str, Any] = Route.structured_output(
                description="JSON schema for output"
            )

        # Create metadata with parameter info
        metadata = ToolMetadata(
            id="test_tool",
            spec_class=TestTool,
            model_config={
                "model_name": "gpt-4.1",
                "adapter_class": "openai",
                "timeout": 300,
            },
            parameters={
                "instructions": ParameterInfo(
                    name="instructions",
                    type=str,
                    type_str="str",
                    route=RouteType.PROMPT,
                    position=None,
                    default=None,
                    required=True,
                    description=None,
                ),
                "structured_output_schema": ParameterInfo(
                    name="structured_output_schema",
                    type=Dict[str, Any],
                    type_str="Dict[str, Any]",
                    route=RouteType.STRUCTURED_OUTPUT,
                    position=None,
                    default=None,
                    required=False,
                    description="JSON schema for output",
                ),
            },
        )

        # Create router and route parameters
        router = ParameterRouter()
        params = {
            "instructions": "Test prompt",
            "structured_output_schema": {
                "type": "object",
                "properties": {"result": {"type": "string"}},
            },
        }

        routed = router.route(metadata, params)

        # Check that schema was routed to structured_output
        assert "structured_output" in routed
        assert (
            routed["structured_output"]["structured_output_schema"]
            == params["structured_output_schema"]
        )

    def test_structured_output_none_is_handled(self):
        """Test that None structured_output_schema is handled correctly."""

        @tool
        class TestTool(ToolSpec):
            model_name = "gpt-4.1"
            adapter_class = "openai"

            instructions: str = Route.prompt()
            structured_output_schema: Dict[str, Any] = Route.structured_output()

        metadata = ToolMetadata(
            id="test_tool",
            spec_class=TestTool,
            model_config={
                "model_name": "gpt-4.1",
                "adapter_class": "openai",
                "timeout": 300,
            },
            parameters={
                "instructions": ParameterInfo(
                    name="instructions",
                    type=str,
                    type_str="str",
                    route=RouteType.PROMPT,
                    position=None,
                    default=None,
                    required=True,
                    description=None,
                ),
                "structured_output_schema": ParameterInfo(
                    name="structured_output_schema",
                    type=Dict[str, Any],
                    type_str="Dict[str, Any]",
                    route=RouteType.STRUCTURED_OUTPUT,
                    position=None,
                    default=None,
                    required=False,
                    description=None,
                ),
            },
        )

        router = ParameterRouter()
        params = {"instructions": "Test prompt", "structured_output_schema": None}

        routed = router.route(metadata, params)

        # None values are skipped by the router
        assert "structured_output" in routed
        # When None, the parameter is not included in routed output
        assert "structured_output_schema" not in routed["structured_output"]

    def test_multiple_tools_with_structured_output(self):
        """Test that multiple tools can have structured output schemas."""

        @tool
        class Tool1(ToolSpec):
            model_name = "gpt-4.1"
            adapter_class = "openai"
            structured_output_schema: Dict[str, Any] = Route.structured_output()

        @tool
        class Tool2(ToolSpec):
            model_name = "gemini-2.5-flash"
            adapter_class = "vertex"
            structured_output_schema: Dict[str, Any] = Route.structured_output()

        # Both tools should be able to use structured output
        assert hasattr(Tool1, "structured_output_schema")
        assert hasattr(Tool2, "structured_output_schema")
