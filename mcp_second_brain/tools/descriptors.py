"""Route descriptors for parameter routing in tool definitions."""

from __future__ import annotations
from typing import Any, Optional, TypeVar, Type, Callable, Generic, overload
from dataclasses import dataclass, field
from enum import Enum

T = TypeVar("T")


class RouteType(Enum):
    PROMPT = "prompt"
    ADAPTER = "adapter"
    VECTOR_STORE = "vector_store"
    SESSION = "session"
    VECTOR_STORE_IDS = "vector_store_ids"
    STRUCTURED_OUTPUT = "structured_output"


@dataclass
class RouteDescriptor(Generic[T]):
    """Descriptor that defines how a parameter is routed during execution.

    Uses default_factory for mutable defaults to avoid shared state between instances.
    """

    route: RouteType
    position: Optional[int] = None
    default: Optional[T] = field(default=None)
    default_factory: Optional[Callable[[], T]] = field(default=None)
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

    def __get__(self, obj: Any, objtype: Optional[Type] = None) -> T:
        """Return the descriptor itself when accessed on the class."""
        if obj is None:
            return self  # type: ignore[return-value]

        # Check if value has been set
        stored_value = getattr(obj, f"_{self.field_name}", None)
        if stored_value is not None:
            return stored_value  # type: ignore[no-any-return]

        # Return default value
        if self.default_factory is not None:
            # Create new instance from factory
            return self.default_factory()
        elif self.default is not None:
            # For immutable defaults, return directly
            return self.default
        else:
            # No default - could be required field
            return None  # type: ignore[return-value]

    def __set__(self, obj: Any, value: T) -> None:
        """Store the value on the instance."""
        setattr(obj, f"_{self.field_name}", value)


class Route:
    """Factory for creating route descriptors."""

    # Overloads for type-safe prompt creation
    @staticmethod
    @overload
    def prompt(
        *,
        pos: Optional[int] = None,
        description: Optional[str] = None,
        default: T,
        default_factory: None = None,
    ) -> RouteDescriptor[T]: ...

    @staticmethod
    @overload
    def prompt(
        *,
        pos: Optional[int] = None,
        description: Optional[str] = None,
        default: None = None,
        default_factory: Callable[[], T],
    ) -> RouteDescriptor[T]: ...

    @staticmethod
    @overload
    def prompt(
        *,
        pos: Optional[int] = None,
        description: Optional[str] = None,
        default: None = None,
        default_factory: None = None,
    ) -> RouteDescriptor[Any]: ...

    @staticmethod
    def prompt(
        pos: Optional[int] = None,
        description: Optional[str] = None,
        default: Any = None,
        default_factory: Optional[Callable[[], Any]] = None,
    ) -> RouteDescriptor:
        """Parameter that goes to the prompt builder."""
        return RouteDescriptor(
            route=RouteType.PROMPT,
            position=pos,
            description=description,
            default=default,
            default_factory=default_factory,
        )

    @staticmethod
    def adapter(
        default: Any = None,
        description: Optional[str] = None,
        default_factory: Optional[Callable[[], Any]] = None,
    ) -> RouteDescriptor:
        """Parameter that goes directly to the model adapter."""
        return RouteDescriptor(
            route=RouteType.ADAPTER,
            default=default,
            default_factory=default_factory,
            description=description,
        )

    @staticmethod
    def vector_store(
        description: Optional[str] = None,
        default_factory: Optional[Callable[[], Any]] = None,
    ) -> RouteDescriptor:
        """Parameter that triggers vector store creation."""
        return RouteDescriptor(
            route=RouteType.VECTOR_STORE,
            default=None,
            default_factory=default_factory,
            description=description,
        )

    @staticmethod
    def session(
        description: Optional[str] = None,
        default_factory: Optional[Callable[[], Any]] = None,
    ) -> RouteDescriptor:
        """Parameter for session management."""
        return RouteDescriptor(
            route=RouteType.SESSION,
            default=None,
            default_factory=default_factory,
            description=description,
        )

    @staticmethod
    def vector_store_ids(
        description: Optional[str] = None,
        default_factory: Optional[Callable[[], Any]] = None,
    ) -> RouteDescriptor:
        """Parameter for passing vector store IDs directly."""
        return RouteDescriptor(
            route=RouteType.VECTOR_STORE_IDS,
            default=None,
            default_factory=default_factory,
            description=description,
        )

    @staticmethod
    def structured_output(
        description: Optional[str] = None,
        default_factory: Optional[Callable[[], Any]] = None,
    ) -> RouteDescriptor:
        """Parameter for structured output schema.

        For OpenAI models, the schema must follow strict validation rules:
        - 'additionalProperties: false' at every object level
        - All properties with constraints (minimum, maximum, enum, pattern) must be listed in 'required'
        """
        return RouteDescriptor(
            route=RouteType.STRUCTURED_OUTPUT,
            default=None,
            default_factory=default_factory,
            description=description,
        )
