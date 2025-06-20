"""Base class for tool specifications."""
from typing import Dict, Any, Type, get_type_hints, get_origin, get_args
from .descriptors import RouteDescriptor


class ToolSpec:
    """Base class for all tool specifications.
    
    Subclasses should define:
    - Class attributes for model configuration
    - Instance attributes with Route descriptors for parameters
    """
    
    # Model configuration (to be overridden by subclasses)
    model_name: str = ""
    adapter_class: str = ""
    context_window: int = 0
    timeout: int = 300
    description: str = ""
    
    @classmethod
    def get_model_config(cls) -> Dict[str, Any]:
        """Get model configuration from class attributes."""
        return {
            "model_name": cls.model_name,
            "adapter_class": cls.adapter_class,
            "context_window": cls.context_window,
            "timeout": cls.timeout,
            "description": cls.description or cls.__doc__ or ""
        }
    
    @classmethod
    def get_parameters(cls) -> Dict[str, Dict[str, Any]]:
        """Extract parameter information from type annotations and descriptors."""
        parameters = {}
        
        # Get type hints for the class
        hints = get_type_hints(cls)
        
        # Iterate through all class attributes
        for name, value in cls.__dict__.items():
            if isinstance(value, RouteDescriptor):
                param_info = {
                    "name": name,
                    "route": value.route,
                    "position": value.position,
                    "default": value.default,
                    "description": value.description,
                    "type": hints.get(name, Any)
                }
                
                # Extract type information
                type_hint = hints.get(name, Any)
                param_info["type_str"] = _type_to_string(type_hint)
                param_info["required"] = not _is_optional(type_hint) and value.default is None
                
                parameters[name] = param_info
        
        return parameters
    
    def get_values(self) -> Dict[str, Any]:
        """Get all parameter values from the instance."""
        values = {}
        params = self.__class__.get_parameters()
        for name in params:
            # Use getattr to properly trigger the descriptor
            values[name] = getattr(self, name, None)
        return values


def _type_to_string(type_hint: Type) -> str:
    """Convert a type hint to a string representation."""
    if hasattr(type_hint, "__name__"):
        return type_hint.__name__
    
    origin = get_origin(type_hint)
    if origin is None:
        return str(type_hint)
    
    args = get_args(type_hint)
    if not args:
        return str(origin.__name__)
    
    arg_strs = [_type_to_string(arg) for arg in args]
    return f"{origin.__name__}[{', '.join(arg_strs)}]"


def _is_optional(type_hint: Type) -> bool:
    """Check if a type hint is Optional (Union with None)."""
    origin = get_origin(type_hint)
    if origin is None:
        return False
    
    # Check for Union types (Optional is Union[T, None])
    from typing import Union
    if origin is Union:
        args = get_args(type_hint)
        return type(None) in args
    
    return False