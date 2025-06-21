"""Route descriptors for parameter routing in tool definitions."""
from typing import Any, Optional, TypeVar, Type, Callable
from dataclasses import dataclass, field

T = TypeVar('T')


@dataclass
class RouteDescriptor:
    """Descriptor that defines how a parameter is routed during execution.
    
    Uses default_factory for mutable defaults to avoid shared state between instances.
    """
    
    route: str  # "prompt", "adapter", "vector_store", "session"
    position: Optional[int] = None
    default: Any = field(default=None)
    default_factory: Optional[Callable[[], Any]] = field(default=None)
    description: Optional[str] = None
    
    def __post_init__(self):
        """Validate that mutable defaults use default_factory."""
        if self.default is not None and self.default_factory is not None:
            raise ValueError("Cannot specify both default and default_factory")
        
        # Check for mutable defaults without factory
        if self.default is not None:
            if isinstance(self.default, (list, dict, set)):
                raise ValueError(
                    f"Mutable default {type(self.default).__name__} should use default_factory. "
                    f"Use default_factory=lambda: {repr(self.default)} instead."
                )
    
    def __set_name__(self, owner: Type, name: str) -> None:
        """Store the field name when the descriptor is bound to a class."""
        self.field_name = name
    
    def __get__(self, obj: Any, objtype: Type = None) -> Any:
        """Return the descriptor itself when accessed on the class."""
        if obj is None:
            return self
        
        # Check if value has been set
        stored_value = getattr(obj, f"_{self.field_name}", None)
        if stored_value is not None:
            return stored_value
        
        # Return default value
        if self.default_factory is not None:
            # Create new instance from factory
            return self.default_factory()
        else:
            # For immutable defaults, return directly
            return self.default
    
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
    def adapter(default: Any = None, description: Optional[str] = None, 
                default_factory: Optional[Callable[[], Any]] = None) -> RouteDescriptor:
        """Parameter that goes directly to the model adapter."""
        return RouteDescriptor(
            route="adapter",
            default=default,
            default_factory=default_factory,
            description=description
        )
    
    @staticmethod
    def vector_store(description: Optional[str] = None,
                     default_factory: Optional[Callable[[], Any]] = None) -> RouteDescriptor:
        """Parameter that triggers vector store creation."""
        return RouteDescriptor(
            route="vector_store",
            default=None,
            default_factory=default_factory,
            description=description
        )
    
    @staticmethod
    def session(description: Optional[str] = None,
                default_factory: Optional[Callable[[], Any]] = None) -> RouteDescriptor:
        """Parameter for session management."""
        return RouteDescriptor(
            route="session",
            default=None,
            default_factory=default_factory,
            description=description
        )