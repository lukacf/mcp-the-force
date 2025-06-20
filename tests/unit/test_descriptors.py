"""
Unit tests for the descriptor-based parameter routing system.
"""
import pytest
from mcp_second_brain.tools.descriptors import RouteDescriptor, Route
from mcp_second_brain.tools.base import ToolSpec


class TestRouteDescriptor:
    """Test the RouteDescriptor class."""
    
    def test_descriptor_metadata(self):
        """Test that descriptors store correct metadata."""
        desc = RouteDescriptor(route="prompt", position=0, description="Test param")
        assert desc.route == "prompt"
        assert desc.position == 0
        assert desc.description == "Test param"
    
    def test_descriptor_with_default(self):
        """Test descriptor with default value."""
        desc = RouteDescriptor(route="adapter", default=0.7)
        assert desc.default == 0.7
        assert desc.default_factory is None
    
    def test_descriptor_with_default_factory(self):
        """Test descriptor with default factory."""
        desc = RouteDescriptor(route="prompt", default_factory=list)
        assert desc.default is None
        assert desc.default_factory is list
        
    def test_descriptor_name_setting(self):
        """Test __set_name__ captures the attribute name."""
        desc = RouteDescriptor(route="prompt")
        
        class TestTool:
            param = desc
        
        # Name should be set when class is created
        assert desc.name == "param"


class TestRoute:
    """Test the Route factory class."""
    
    def test_prompt_route(self):
        """Test Route.prompt() creates correct descriptor."""
        desc = Route.prompt(pos=0, description="Instructions")
        assert isinstance(desc, RouteDescriptor)
        assert desc.route == "prompt"
        assert desc.position == 0
        assert desc.description == "Instructions"
    
    def test_adapter_route(self):
        """Test Route.adapter() creates correct descriptor."""
        desc = Route.adapter(default=0.5, description="Temperature")
        assert desc.route == "adapter"
        assert desc.default == 0.5
        assert desc.description == "Temperature"
    
    def test_vector_store_route(self):
        """Test Route.vector_store() creates correct descriptor."""
        desc = Route.vector_store(description="Attachments")
        assert desc.route == "vector_store"
        assert desc.description == "Attachments"
    
    def test_session_route(self):
        """Test Route.session() creates correct descriptor."""
        desc = Route.session(description="Session ID")
        assert desc.route == "session"
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
        assert TestTool.instructions.route == "prompt"
        assert TestTool.temperature.default == 0.7
    
    def test_descriptor_get_on_instance(self):
        """Test descriptor __get__ on instance returns value."""
        class TestTool(ToolSpec):
            value = Route.prompt(pos=0, default="default_value")
        
        tool = TestTool()
        # Should return default value
        assert tool.value == "default_value"
        
        # Set a value
        tool.value = "new_value"
        assert tool.value == "new_value"
    
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
        assert ComplexTool.inst.name == "inst"
        assert ComplexTool.fmt.name == "fmt"
        assert ComplexTool.ctx.name == "ctx"
        assert ComplexTool.temp.name == "temp"
        assert ComplexTool.attach.name == "attach"
        assert ComplexTool.sess.name == "sess"