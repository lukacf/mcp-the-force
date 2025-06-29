"""Test typed descriptors functionality."""

from typing import List
from mcp_second_brain.tools.base import ToolSpec
from mcp_second_brain.tools.descriptors import Route, RouteDescriptor, RouteType
from mcp_second_brain.tools.registry import tool


class TestTypedDescriptors:
    """Test that typed descriptors work without type ignores."""

    def test_route_descriptor_generics(self):
        """Test that RouteDescriptor preserves types."""
        # Test with default value
        str_route: RouteDescriptor[str] = Route.prompt(default="hello")
        assert str_route.default == "hello"

        # Test with default factory
        list_route: RouteDescriptor[List[str]] = Route.prompt(
            default_factory=lambda: ["a", "b"]
        )
        assert list_route.default_factory is not None
        assert list_route.default_factory() == ["a", "b"]

    def test_toolspec_type_preservation(self):
        """Test that ToolSpec preserves field types without type ignores."""

        @tool
        class TestTool(ToolSpec):
            """Test tool with typed fields."""

            model_name = "test"
            adapter_class = "test"
            context_window = 100
            timeout = 1

            # These should not need type: ignore anymore
            text: str = Route.prompt(description="Text field")
            count: int = Route.prompt(description="Count", default=10)
            items: List[str] = Route.prompt(
                description="Items", default_factory=lambda: ["default"]
            )

        # Create instance
        instance = TestTool()

        # Types should be preserved
        instance.text = "hello"
        instance.count = 20
        instance.items = ["one", "two"]

        # Get values
        values = instance.get_values()
        assert values["text"] == "hello"
        assert values["count"] == 20
        assert values["items"] == ["one", "two"]

    def test_dataclass_transform_compatibility(self):
        """Test that dataclass_transform allows proper type checking."""
        # This test verifies that mypy would be happy with our usage
        # In a real mypy run, these would not generate errors

        @tool
        class MyTool(ToolSpec):
            """Tool using all route types."""

            model_name = "test"
            adapter_class = "test"
            context_window = 100

            # All of these should type-check properly
            prompt_field: str = Route.prompt(description="Prompt")
            adapter_field: float = Route.adapter(default=0.5)
            vector_field: List[str] = Route.vector_store(default_factory=list)
            session_field: str = Route.session()
            vs_ids_field: List[str] = Route.vector_store_ids(default_factory=list)

        my_tool_instance = MyTool()

        # Verify field access works
        my_tool_instance.prompt_field = "test"
        my_tool_instance.adapter_field = 0.7
        my_tool_instance.vector_field = ["/path/to/files"]
        my_tool_instance.session_field = "session-123"
        my_tool_instance.vs_ids_field = ["vs_123", "vs_456"]

        # Verify parameters are extracted correctly
        params = MyTool.get_parameters()
        assert "prompt_field" in params
        assert params["prompt_field"]["route"] == RouteType.PROMPT
        assert params["prompt_field"]["type_str"] == "str"

        assert "adapter_field" in params
        assert params["adapter_field"]["route"] == RouteType.ADAPTER
        assert params["adapter_field"]["type_str"] == "float"

        assert "vector_field" in params
        assert params["vector_field"]["route"] == RouteType.VECTOR_STORE
        assert params["vector_field"]["type_str"] in ["List[str]", "list[str]"]

    def test_descriptor_default_handling(self):
        """Test that descriptors handle defaults correctly."""

        class TestDefaults(ToolSpec):
            model_name = "test"
            adapter_class = "test"

            # No default - should return None
            required: str = Route.prompt(description="Required field")

            # With default value
            with_default: int = Route.prompt(default=42)

            # With default factory
            with_factory: List[str] = Route.prompt(
                default_factory=lambda: ["a", "b", "c"]
            )

        instance = TestDefaults()

        # Required field should be None when not set
        assert getattr(instance, "required", "NOT_SET") is None

        # Default value should work
        assert instance.with_default == 42

        # Default factory should create new instance each time
        list1 = instance.with_factory
        list2 = instance.with_factory
        assert list1 == ["a", "b", "c"]
        assert list2 == ["a", "b", "c"]
        assert list1 is not list2  # Should be different instances
