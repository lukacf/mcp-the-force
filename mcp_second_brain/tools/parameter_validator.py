"""Parameter validation for tools."""
import logging
from typing import Dict, Any
from .registry import ToolMetadata
from .base import ToolSpec

logger = logging.getLogger(__name__)


class ParameterValidator:
    """Handles parameter validation for tools."""
    
    def __init__(self, strict_mode: bool = False):
        """Initialize validator.
        
        Args:
            strict_mode: If True, raise errors for unknown parameters.
                        If False (default), log warnings only.
        """
        self.strict_mode = strict_mode
    
    def validate(
        self, 
        tool_instance: ToolSpec, 
        metadata: ToolMetadata, 
        kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate parameters and set them on the tool instance.
        
        Args:
            tool_instance: Instance of the tool
            metadata: Tool metadata containing parameter info
            kwargs: User-provided arguments
            
        Returns:
            Dict of validated parameters
            
        Raises:
            ValueError: If required parameter missing or unknown parameter in strict mode
        """
        validated = {}
        
        # Check required parameters
        for name, param_info in metadata.parameters.items():
            if param_info.required and name not in kwargs:
                raise ValueError(f"Missing required parameter: {name}")
            
            # Get value or use default
            if name in kwargs:
                value = kwargs[name]
            else:
                value = param_info.default
            
            # Check that required parameters are not None
            if param_info.required and value is None:
                raise ValueError(f"Required parameter '{name}' cannot be None")
            
            # TODO: Add type validation here if needed
            # if not isinstance(value, param_info.type):
            #     raise TypeError(f"Parameter '{name}' expected {param_info.type}, got {type(value)}")
            
            # Set on instance (descriptor will handle storage)
            setattr(tool_instance, name, value)
            validated[name] = value
        
        # Check for unknown parameters
        known_params = set(metadata.parameters.keys())
        unknown = set(kwargs.keys()) - known_params
        if unknown:
            if self.strict_mode:
                raise ValueError(f"Unknown parameters: {unknown}")
            else:
                logger.warning(f"Unknown parameters will be ignored: {unknown}")
        
        return validated