"""Tool registry and decorator for automatic tool registration."""

from typing import Type, Dict, Any, Callable, TypeVar, List
from dataclasses import dataclass, field
import logging
from .base import ToolSpec
from .descriptors import RouteType

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=ToolSpec)

# Global registry of all tools
TOOL_REGISTRY: Dict[str, "ToolMetadata"] = {}


def _ensure_populated() -> None:
    """Ensure tools are registered by importing definitions if needed."""
    if TOOL_REGISTRY:  # already loaded
        return
    # Importing this module registers every tool class via the @tool decorator
    from . import definitions  # noqa: F401


@dataclass
class ParameterInfo:
    """Information about a tool parameter."""

    name: str
    type: Type
    type_str: str
    route: RouteType
    position: int | None
    default: Any
    required: bool
    description: str | None


@dataclass
class ToolMetadata:
    """Metadata about a registered tool."""

    id: str
    spec_class: Type[ToolSpec]
    parameters: Dict[str, ParameterInfo]
    model_config: Dict[str, Any]
    aliases: List[str] = field(default_factory=list)
    capabilities: Dict[str, Any] = field(default_factory=dict)


def tool(
    cls: Type[T] | None = None, *, aliases: List[str] | None = None
) -> Type[T] | Callable[[Type[T]], Type[T]]:
    """Decorator that registers a tool specification.

    Usage:
        @tool
        class MyTool(ToolSpec):
            ...

        @tool(aliases=["my-alias", "another-alias"])
        class MyTool(ToolSpec):
            ...
    """

    def decorator(cls: Type[T]) -> Type[T]:
        if not issubclass(cls, ToolSpec):
            raise TypeError(f"{cls.__name__} must inherit from ToolSpec")

        # Extract tool ID from class name (convert CamelCase to snake_case)
        tool_id = _camel_to_snake(cls.__name__)

        # Get model configuration
        model_config = cls.get_model_config()
        # Allow local tools to signal via explicit adapter_class=None
        adapter_value = model_config.get("adapter_class")
        explicit_adapter = "adapter_class" in cls.__dict__
        # For non-local tools, enforce both model_name and adapter_class are defined
        if not (explicit_adapter and adapter_value is None):
            if not model_config.get("model_name"):
                raise ValueError(f"{cls.__name__} must define model_name")
            if not adapter_value:
                raise ValueError(f"{cls.__name__} must define adapter_class")

        # Extract parameters
        parameters = {}
        positions_used: Dict[int, str] = {}

        for name, param_info in cls.get_parameters().items():
            # Validate position uniqueness
            pos = param_info["position"]
            if pos is not None:
                if pos in positions_used:
                    raise ValueError(
                        f"{cls.__name__}: Position {pos} used by both "
                        f"'{positions_used[pos]}' and '{name}'"
                    )
                positions_used[pos] = name

            parameters[name] = ParameterInfo(
                name=name,
                type=param_info["type"],
                type_str=param_info["type_str"],
                route=param_info["route"],
                position=param_info["position"],
                default=param_info["default"],
                required=param_info["required"],
                description=param_info["description"],
            )

        # Create metadata
        metadata = ToolMetadata(
            id=tool_id,
            spec_class=cls,
            parameters=parameters,
            model_config=model_config,
            aliases=aliases or [],
            capabilities={},
        )

        # Set memory capability based on model
        model_name = model_config.get("model_name", "")
        if model_name in [
            "o3",
            "o3-pro",
            "gpt-4.1",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "grok-4",
            "grok-3-beta",
        ]:
            metadata.capabilities["writes_memory"] = True

        # Register the tool
        TOOL_REGISTRY[tool_id] = metadata
        logger.debug(f"Registered tool: {tool_id}")

        # Register aliases
        # Note: Aliases share the same metadata object reference as the primary tool.
        # This is intentional - aliases are just alternative names for the same tool.
        if aliases:
            for alias in aliases:
                TOOL_REGISTRY[alias] = metadata  # Same metadata object, not a copy
                logger.debug(f"Registered alias: {alias} -> {tool_id}")

        # Store metadata on the class for easy access
        cls._tool_metadata = metadata  # type: ignore[attr-defined]

        return cls

    # Handle @tool without parentheses
    if cls is not None:
        return decorator(cls)

    return decorator


def get_tool(tool_id: str) -> ToolMetadata | None:
    """Get tool metadata by ID."""
    _ensure_populated()
    return TOOL_REGISTRY.get(tool_id)


def list_tools() -> Dict[str, ToolMetadata]:
    """Get all registered tools."""
    _ensure_populated()
    return TOOL_REGISTRY.copy()


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            # Add underscore before uppercase letter if:
            # - Previous char is lowercase
            # - Or next char is lowercase (handles acronyms)
            if name[i - 1].islower() or (i < len(name) - 1 and name[i + 1].islower()):
                result.append("_")
        result.append(char.lower())
    return "".join(result)
