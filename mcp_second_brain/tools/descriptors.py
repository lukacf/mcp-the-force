"""Route descriptors for parameter routing in tool definitions."""
from typing import Any, Optional, TypeVar, Type
from dataclasses import dataclass, field

T = TypeVar('T')


@dataclass
class RouteDescriptor:
    """Descriptor that defines how a parameter is routed during execution.
    
    Warning: Mutable default values (lists, dicts) will be shared between instances.
    Use None as default and handle initialization in the tool if you need mutable defaults.
    """
    
    route: str  # "prompt", "adapter", "vector_store", "session"
    position: Optional[int] = None
    default: Any = field(default=None)  # Warning: mutable defaults are shared!
    description: Optional[str] = None
    
    def __set_name__(self, owner: Type, name: str) -> None:
        """Store the field name when the descriptor is bound to a class."""
        self.field_name = name
    
    def __get__(self, obj: Any, objtype: Type = None) -> Any:
        """Return the descriptor itself when accessed on the class."""
        if obj is None:
            return self
        # Return the actual value from the instance
        return getattr(obj, f"_{self.field_name}", self.default)
    
    def __set__(self, obj: Any, value: Any) -> None:
        """Store the value on the instance."""
        setattr(obj, f"_{self.field_name}", value)


class Route:
    """Factory for creating route descriptors."""
    
    @staticmethod
    def prompt(pos: Optional[int] = None, description: Optional[str] = None) -> RouteDescriptor:
        """Parameter that goes to the prompt builder."""
        return RouteDescriptor(
            route="prompt",
            position=pos,
            description=description
        )
    
    @staticmethod
    def adapter(default: Any = None, description: Optional[str] = None) -> RouteDescriptor:
        """Parameter that goes directly to the model adapter."""
        return RouteDescriptor(
            route="adapter",
            default=default,
            description=description
        )
    
    @staticmethod
    def vector_store(description: Optional[str] = None) -> RouteDescriptor:
        """Parameter that triggers vector store creation."""
        return RouteDescriptor(
            route="vector_store",
            default=None,
            description=description
        )
    
    @staticmethod
    def session(description: Optional[str] = None) -> RouteDescriptor:
        """Parameter for session management."""
        return RouteDescriptor(
            route="session",
            default=None,
            description=description
        )