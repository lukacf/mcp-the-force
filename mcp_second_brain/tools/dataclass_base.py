"""Alternative implementation using actual dataclasses with field metadata."""
from dataclasses import dataclass, field, fields
from typing import Dict, Any, Optional, get_type_hints, get_origin, get_args


@dataclass
class ToolSpec:
    """Base class for tool specifications using dataclasses.
    
    This implementation uses dataclasses.field(metadata=...) instead of custom descriptors.
    """
    
    # Model configuration (class attributes)
    model_name: str = ""
    adapter_class: str = ""
    context_window: int = 0
    timeout: int = 300
    description: str = ""
    prompt_template: Optional[str] = None
    
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
        """Extract parameter information from dataclass fields."""
        parameters = {}
        
        # Get fields from dataclass
        for field_info in fields(cls):
            # Skip if no metadata
            metadata = field_info.metadata
            if not metadata or "route" not in metadata:
                continue
            
            param_info = {
                "name": field_info.name,
                "route": metadata["route"],
                "position": metadata.get("position"),
                "default": field_info.default if field_info.default is not field_info.default_factory else None,
                "description": metadata.get("description", ""),
                "type": field_info.type
            }
            
            # Extract type information
            param_info["type_str"] = _type_to_string(field_info.type)
            param_info["required"] = field_info.default is field_info.default_factory and not _is_optional(field_info.type)
            
            parameters[field_info.name] = param_info
        
        return parameters
    
    def get_values(self) -> Dict[str, Any]:
        """Get all parameter values from the instance."""
        values = {}
        for field_info in fields(self):
            if field_info.metadata and "route" in field_info.metadata:
                values[field_info.name] = getattr(self, field_info.name)
        return values


def route_field(
    route: str,
    *,
    position: Optional[int] = None,
    description: str = "",
    default: Any = field(default=None)
) -> Any:
    """Helper to create a field with routing metadata.
    
    Args:
        route: Route type ("prompt", "adapter", "vector_store", "session")
        position: Optional position for ordered prompt parameters
        description: Field description
        default: Default value or field() instance
    
    Returns:
        A dataclass field with routing metadata
    """
    # If default is already a field, add metadata to it
    if hasattr(default, 'metadata'):
        metadata = {**default.metadata}
    else:
        metadata = {}
    
    metadata.update({
        "route": route,
        "position": position,
        "description": description
    })
    
    if hasattr(default, 'default') or hasattr(default, 'default_factory'):
        # It's already a field instance
        return field(
            default=default.default if hasattr(default, 'default') else field.default,
            default_factory=default.default_factory if hasattr(default, 'default_factory') else field.default_factory,
            metadata=metadata
        )
    else:
        # It's a regular default value
        return field(default=default, metadata=metadata)


# Convenience route helpers
class RouteField:
    """Convenience methods for creating routed fields."""
    
    @staticmethod
    def prompt(pos: Optional[int] = None, description: str = "", default: Any = None):
        """Create a prompt-routed field."""
        return route_field("prompt", position=pos, description=description, default=default)
    
    @staticmethod
    def adapter(description: str = "", default: Any = None):
        """Create an adapter-routed field."""
        return route_field("adapter", description=description, default=default)
    
    @staticmethod
    def vector_store(description: str = "", default: Any = None):
        """Create a vector_store-routed field."""
        return route_field("vector_store", description=description, default=default)
    
    @staticmethod
    def session(description: str = "", default: Any = None):
        """Create a session-routed field."""
        return route_field("session", description=description, default=default)


def _type_to_string(type_hint) -> str:
    """Convert a type hint to a string representation."""
    from typing import Union, Literal
    
    origin = get_origin(type_hint)
    args = get_args(type_hint)
    
    # Handle parameterized generics first
    if origin is not None:
        # Special handling for Optional (Union with None)
        if origin is Union and type(None) in args:
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                return f"Optional[{_type_to_string(non_none_args[0])}]"
            else:
                arg_strs = [_type_to_string(arg) for arg in args]
                return f"Union[{', '.join(arg_strs)}]"
        
        # Special handling for Literal types
        if origin is Literal:
            literal_values = ", ".join(repr(arg) for arg in args)
            return f"Literal[{literal_values}]"
        
        # Other generics
        if args:
            arg_strs = [_type_to_string(arg) for arg in args]
            origin_str = origin.__name__ if hasattr(origin, "__name__") else str(origin)
            return f"{origin_str}[{', '.join(arg_strs)}]"
        else:
            return origin.__name__ if hasattr(origin, "__name__") else str(origin)
    
    # Non-parameterized types
    if isinstance(type_hint, type):
        return type_hint.__name__
    
    # Fallback
    return str(type_hint).replace("typing.", "")


def _is_optional(type_hint) -> bool:
    """Check if a type hint is Optional (Union with None)."""
    origin = get_origin(type_hint)
    if origin is None:
        return False
    
    from typing import Union
    if origin is Union:
        args = get_args(type_hint)
        return type(None) in args
    
    # Handle Python 3.10+ union syntax
    import sys
    if sys.version_info >= (3, 10):
        import types
        if isinstance(type_hint, types.UnionType):
            return type(None) in get_args(type_hint)
    
    return False