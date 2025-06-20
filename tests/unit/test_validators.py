"""
Unit tests for parameter validation.
"""
import pytest
from typing import Optional, List
from mcp_second_brain.tools.parameter_validator import ParameterValidator
from mcp_second_brain.tools.registry import ToolMetadata, ParameterInfo
from mcp_second_brain.tools.base import ToolSpec
from mcp_second_brain.tools.descriptors import Route


class TestParameterValidator:
    """Test the ParameterValidator class."""
    
    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return ParameterValidator(strict_mode=False)
    
    @pytest.fixture
    def strict_validator(self):
        """Create a strict validator instance."""
        return ParameterValidator(strict_mode=True)
    
    @pytest.fixture
    def sample_tool_class(self):
        """Create a sample tool class for testing."""
        class TestTool(ToolSpec):
            # Required parameters
            instructions: str = Route.prompt(pos=0, description="Instructions")
            output_format: str = Route.prompt(pos=1, description="Format")
            context: List[str] = Route.prompt(pos=2, description="Context files")
            
            # Optional parameters
            temperature: Optional[float] = Route.adapter(default=0.7, description="Temperature")
            session_id: Optional[str] = Route.session(description="Session ID")
        
        return TestTool
    
    @pytest.fixture
    def tool_metadata(self):
        """Create metadata for the test tool."""
        return ToolMetadata(
            name="test_tool",
            description="Test tool",
            parameters={
                "instructions": ParameterInfo(
                    name="instructions",
                    type="str",
                    required=True,
                    description="Instructions"
                ),
                "output_format": ParameterInfo(
                    name="output_format",
                    type="str",
                    required=True,
                    description="Format"
                ),
                "context": ParameterInfo(
                    name="context",
                    type="List[str]",
                    required=True,
                    description="Context files"
                ),
                "temperature": ParameterInfo(
                    name="temperature",
                    type="Optional[float]",
                    required=False,
                    description="Temperature"
                ),
                "session_id": ParameterInfo(
                    name="session_id",
                    type="Optional[str]",
                    required=False,
                    description="Session ID"
                ),
            }
        )
    
    def test_validate_all_required_params(self, validator, sample_tool_class, tool_metadata):
        """Test validation with all required parameters provided."""
        tool = sample_tool_class()
        kwargs = {
            "instructions": "Test instruction",
            "output_format": "json",
            "context": ["file1.py", "file2.py"]
        }
        
        result = validator.validate(tool, tool_metadata, kwargs)
        
        # Check all required params are validated
        assert "instructions" in result
        assert "output_format" in result
        assert "context" in result
        
        # Check values are set on tool instance
        assert tool.instructions == "Test instruction"
        assert tool.output_format == "json"
        assert tool.context == ["file1.py", "file2.py"]
    
    def test_missing_required_param(self, validator, sample_tool_class, tool_metadata):
        """Test that missing required parameter raises error."""
        tool = sample_tool_class()
        kwargs = {
            "instructions": "Test",
            # Missing output_format and context
        }
        
        with pytest.raises(ValueError, match="Missing required parameter: output_format"):
            validator.validate(tool, tool_metadata, kwargs)
    
    def test_optional_param_with_default(self, validator, sample_tool_class, tool_metadata):
        """Test optional parameter uses default when not provided."""
        tool = sample_tool_class()
        kwargs = {
            "instructions": "Test",
            "output_format": "text",
            "context": []
        }
        
        result = validator.validate(tool, tool_metadata, kwargs)
        
        # Temperature should use default value
        assert tool.temperature == 0.7
    
    def test_optional_param_override(self, validator, sample_tool_class, tool_metadata):
        """Test optional parameter can be overridden."""
        tool = sample_tool_class()
        kwargs = {
            "instructions": "Test",
            "output_format": "text",
            "context": [],
            "temperature": 0.9
        }
        
        result = validator.validate(tool, tool_metadata, kwargs)
        
        # Temperature should use provided value
        assert tool.temperature == 0.9
    
    def test_unknown_param_lenient_mode(self, validator, sample_tool_class, tool_metadata):
        """Test unknown parameter in lenient mode (just warns)."""
        tool = sample_tool_class()
        kwargs = {
            "instructions": "Test",
            "output_format": "text",
            "context": [],
            "unknown_param": "value"  # This is not defined
        }
        
        # Should not raise in lenient mode
        result = validator.validate(tool, tool_metadata, kwargs)
        
        # Unknown param should not be in result
        assert "unknown_param" not in result
    
    def test_unknown_param_strict_mode(self, strict_validator, sample_tool_class, tool_metadata):
        """Test unknown parameter in strict mode (raises error)."""
        tool = sample_tool_class()
        kwargs = {
            "instructions": "Test",
            "output_format": "text",
            "context": [],
            "unknown_param": "value"  # This is not defined
        }
        
        # Should raise in strict mode
        with pytest.raises(ValueError, match="Unknown parameter: unknown_param"):
            strict_validator.validate(tool, tool_metadata, kwargs)
    
    def test_type_validation_basic(self, validator, sample_tool_class, tool_metadata):
        """Test basic type validation."""
        tool = sample_tool_class()
        
        # Wrong type for temperature (string instead of float)
        kwargs = {
            "instructions": "Test",
            "output_format": "text",
            "context": [],
            "temperature": "high"  # Should be float
        }
        
        with pytest.raises(ValueError, match="Invalid type for parameter temperature"):
            validator.validate(tool, tool_metadata, kwargs)
    
    def test_list_type_validation(self, validator, sample_tool_class, tool_metadata):
        """Test list type validation."""
        tool = sample_tool_class()
        
        # Wrong type for context (string instead of list)
        kwargs = {
            "instructions": "Test",
            "output_format": "text",
            "context": "file.py"  # Should be list
        }
        
        with pytest.raises(ValueError, match="Invalid type for parameter context"):
            validator.validate(tool, tool_metadata, kwargs)
    
    def test_empty_kwargs(self, validator, sample_tool_class, tool_metadata):
        """Test validation with empty kwargs."""
        tool = sample_tool_class()
        kwargs = {}
        
        # Should fail on first missing required param
        with pytest.raises(ValueError, match="Missing required parameter"):
            validator.validate(tool, tool_metadata, kwargs)
    
    def test_none_value_for_optional(self, validator, sample_tool_class, tool_metadata):
        """Test that None is accepted for optional parameters."""
        tool = sample_tool_class()
        kwargs = {
            "instructions": "Test",
            "output_format": "text",
            "context": [],
            "session_id": None  # Explicitly None
        }
        
        result = validator.validate(tool, tool_metadata, kwargs)
        
        # Should accept None for optional param
        assert tool.session_id is None