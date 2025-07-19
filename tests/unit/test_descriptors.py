"""
Unit tests for the descriptor-based parameter routing system.
"""

from mcp_second_brain.tools.descriptors import RouteDescriptor, Route, RouteType
from mcp_second_brain.tools.base import ToolSpec


class TestRouteDescriptor:
    """Test the RouteDescriptor class."""

    def test_descriptor_metadata(self):
        """Test that descriptors store correct metadata."""
        desc = RouteDescriptor(
            route=RouteType.PROMPT, position=0, description="Test param"
        )
        assert desc.route == RouteType.PROMPT
        assert desc.position == 0
        assert desc.description == "Test param"

    def test_descriptor_with_default(self):
        """Test descriptor with default value."""
        desc = RouteDescriptor(route=RouteType.ADAPTER, default=0.7)
        assert desc.default == 0.7
        assert desc.default_factory is None

    def test_descriptor_with_default_factory(self):
        """Test descriptor with default factory."""
        from mcp_second_brain.tools.descriptors import _NO_DEFAULT

        desc = RouteDescriptor(route=RouteType.PROMPT, default_factory=list)
        assert desc.default is _NO_DEFAULT
        assert desc.default_factory is list

    def test_descriptor_name_setting(self):
        """Test __set_name__ captures the attribute name."""
        desc = RouteDescriptor(route=RouteType.PROMPT)

        class TestTool:
            param = desc

        # Name should be set when class is created
        assert desc.field_name == "param"

    def test_has_default_property(self):
        """Test has_default property correctly identifies defaults."""
        from mcp_second_brain.tools.descriptors import _NO_DEFAULT

        # No default
        desc1 = RouteDescriptor(route=RouteType.PROMPT)
        assert desc1.default is _NO_DEFAULT
        assert not desc1.has_default

        # With default value
        desc2 = RouteDescriptor(route=RouteType.PROMPT, default=None)
        assert desc2.default is None
        assert desc2.has_default

        # With default factory
        desc3 = RouteDescriptor(route=RouteType.PROMPT, default_factory=list)
        assert desc3.default is _NO_DEFAULT
        assert desc3.has_default


class TestRoute:
    """Test the Route factory class."""

    def test_prompt_route(self):
        """Test Route.prompt() creates correct descriptor."""
        desc = Route.prompt(pos=0, description="Instructions")
        assert isinstance(desc, RouteDescriptor)
        assert desc.route == RouteType.PROMPT
        assert desc.position == 0
        assert desc.description == "Instructions"

    def test_adapter_route(self):
        """Test Route.adapter() creates correct descriptor."""
        desc = Route.adapter(default=0.5, description="Temperature")
        assert desc.route == RouteType.ADAPTER
        assert desc.default == 0.5
        assert desc.description == "Temperature"

    def test_vector_store_route(self):
        """Test Route.vector_store() creates correct descriptor."""
        desc = Route.vector_store(description="Attachments")
        assert desc.route == RouteType.VECTOR_STORE
        assert desc.description == "Attachments"

    def test_session_route(self):
        """Test Route.session() creates correct descriptor."""
        desc = Route.session(description="Session ID")
        assert desc.route == RouteType.SESSION
        assert desc.description == "Session ID"


class TestDescriptorIntegration:
    """Test descriptors integrated with ToolSpec classes."""

    def test_tool_spec_with_descriptors(self):
        """Test that ToolSpec classes work with descriptors."""

        class TestTool(ToolSpec):
            instructions = Route.prompt(pos=0, description="Task instructions")
            temperature = Route.adapter(default=0.7, description="Sampling temp")
            attachments = Route.vector_store(description="Files for RAG")
            session_id = Route.session(description="Session ID")

        # Check class-level access returns descriptors
        assert isinstance(TestTool.instructions, RouteDescriptor)
        assert TestTool.instructions.route == RouteType.PROMPT
        assert TestTool.temperature.default == 0.7

    def test_descriptor_get_on_instance(self):
        """Test descriptor __get__ on instance returns value."""

        class TestTool(ToolSpec):
            value = Route.prompt(pos=0)
            temp = Route.adapter(default=0.7)

        tool = TestTool()
        # Prompt params don't have defaults
        assert tool.value is None

        # Adapter params can have defaults
        assert tool.temp == 0.7

        # Set values
        tool.value = "new_value"
        tool.temp = 0.9
        assert tool.value == "new_value"
        assert tool.temp == 0.9

    def test_all_descriptors_get_names(self):
        """Test that all descriptors in a class get their names set."""

        class ComplexTool(ToolSpec):
            inst = Route.prompt(pos=0)
            fmt = Route.prompt(pos=1)
            ctx = Route.prompt(pos=2)
            temp = Route.adapter()
            attach = Route.vector_store()
            sess = Route.session()

        # All descriptors should have their names set
        assert ComplexTool.inst.field_name == "inst"
        assert ComplexTool.fmt.field_name == "fmt"
        assert ComplexTool.ctx.field_name == "ctx"
        assert ComplexTool.temp.field_name == "temp"
        assert ComplexTool.attach.field_name == "attach"
        assert ComplexTool.sess.field_name == "sess"


class TestTypedDescriptors:
    """Test typed descriptor functionality."""

    def test_route_descriptor_generics(self):
        """Test that RouteDescriptor preserves types."""
        from typing import List

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
        from typing import List
        from mcp_second_brain.tools.registry import tool

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
        from typing import List
        from mcp_second_brain.tools.registry import tool

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

    def test_descriptor_default_factory_behavior(self):
        """Test that descriptor default factories create new instances."""
        from typing import List

        class TestDefaults(ToolSpec):
            model_name = "test"
            adapter_class = "test"

            # With default factory
            with_factory: List[str] = Route.prompt(
                default_factory=lambda: ["a", "b", "c"]
            )

        instance = TestDefaults()

        # Default factory should create new instance each time
        list1 = instance.with_factory
        list2 = instance.with_factory
        assert list1 == ["a", "b", "c"]
        assert list2 == ["a", "b", "c"]
        assert list1 is not list2  # Should be different instances
