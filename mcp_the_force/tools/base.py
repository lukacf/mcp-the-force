"""Base class for tool specifications."""

from typing import (
    Dict,
    Any,
    Type,
    get_type_hints,
    get_origin,
    get_args,
    ClassVar,
    Optional,
    TYPE_CHECKING,
)
from typing_extensions import dataclass_transform
from .descriptors import RouteDescriptor, Route, _NO_DEFAULT

if TYPE_CHECKING:
    from .registry import ToolMetadata


@dataclass_transform(
    field_specifiers=(
        Route.prompt,
        Route.adapter,
        Route.vector_store,
        Route.session,
        Route.vector_store_ids,
    )
)
class ToolSpec:
    """Base class for all tool specifications.

    Subclasses should define:
    - Class attributes for model configuration
    - Instance attributes with Route descriptors for parameters
    - Optional prompt_template for custom prompt formatting
    """

    # Model configuration (to be overridden by subclasses)
    model_name: str = ""
    adapter_class: str | None = None
    context_window: int = 0
    timeout: int = 600  # Default timeout 10 minutes
    description: str = ""

    # Internal-only tools are in TOOL_REGISTRY but not exposed via MCP
    # Used for chat_with_* tools that consult_with routes to internally
    internal_only: bool = False

    # LocalService class (optional, for utility tools)
    service_cls: type | None = None

    # Prompt template (optional, uses default if not provided)
    prompt_template: str | None = None

    # Tool metadata (set by @tool decorator)
    _tool_metadata: ClassVar[Optional["ToolMetadata"]] = None

    @classmethod
    def get_model_config(cls) -> Dict[str, Any]:
        """Get model configuration from class attributes."""
        config = {
            "model_name": cls.model_name,
            "adapter_class": cls.adapter_class,
            "context_window": cls.context_window,
            "timeout": cls.timeout,
            "description": cls.description,
            "internal_only": cls.internal_only,
        }
        # Include service_cls if defined (for LocalService pattern)
        if hasattr(cls, "service_cls") and cls.service_cls is not None:
            config["service_cls"] = cls.service_cls  # type: ignore[assignment]
        return config

    @classmethod
    def get_parameters(cls) -> Dict[str, Dict[str, Any]]:
        """Extract parameter information from type annotations and descriptors."""
        parameters = {}

        # Import here to avoid circular import
        from .registry import ToolMetadata

        # Get type hints for the class, providing ToolMetadata in localns
        hints = get_type_hints(cls, localns={"ToolMetadata": ToolMetadata})

        # Iterate through all class attributes
        for name, value in cls.__dict__.items():
            if isinstance(value, RouteDescriptor):
                param_info = {
                    "name": name,
                    "route": value.route,
                    "position": value.position,
                    "default": None if value.default is _NO_DEFAULT else value.default,
                    "default_factory": value.default_factory,
                    "description": value.description,
                    "type": hints.get(name, Any),
                    "requires_capability": value.requires_capability,
                }

                # Extract type information
                type_hint = hints.get(name, Any)
                param_info["type_str"] = _type_to_string(type_hint)
                param_info["required"] = (
                    not _is_optional(type_hint) and not value.has_default
                )

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
    from typing import Union, Literal

    origin = get_origin(type_hint)
    args = get_args(type_hint)

    # Handle parameterized generics first (they have an origin)
    if origin is not None:
        # Special handling for Optional (Union with None)
        if origin is Union and type(None) in args:
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                # Simple Optional[T]
                return f"Optional[{_type_to_string(non_none_args[0])}]"
            else:
                # Union with multiple non-None types
                arg_strs = [_type_to_string(arg) for arg in args]
                return f"Union[{', '.join(arg_strs)}]"

        # Special handling for Literal types
        if origin is Literal:
            literal_values = ", ".join(repr(arg) for arg in args)
            return f"Literal[{literal_values}]"

        # Other generics (List[int], Dict[str, float], etc.)
        if args:
            arg_strs = [_type_to_string(arg) for arg in args]
            origin_str = origin.__name__ if hasattr(origin, "__name__") else str(origin)
            return f"{origin_str}[{', '.join(arg_strs)}]"
        else:
            # Generic without args
            return origin.__name__ if hasattr(origin, "__name__") else str(origin)  # type: ignore[no-any-return]

    # Non-parameterized types
    if isinstance(type_hint, type):
        # Plain class (int, str, etc.)
        return type_hint.__name__

    # Fallback for other typing constructs
    return str(type_hint).replace("typing.", "")


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

    # Handle Python 3.10+ union syntax (str | None)
    import sys

    if sys.version_info >= (3, 10):
        import types

        if isinstance(type_hint, types.UnionType):
            return type(None) in get_args(type_hint)

    return False
