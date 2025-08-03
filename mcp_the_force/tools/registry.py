"""Tool registry and decorator for automatic tool registration."""

from typing import Type, Dict, Any, Callable, TypeVar, List, Optional
from dataclasses import dataclass, field
import logging
from .base import ToolSpec
from .descriptors import RouteType
from ..adapters.capabilities import AdapterCapabilities

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=ToolSpec)

# Global registry of all tools
TOOL_REGISTRY: Dict[str, "ToolMetadata"] = {}


_autogen_loaded = False


def _ensure_populated() -> None:
    """Ensure tools are registered by importing definitions if needed."""
    global _autogen_loaded

    # Always check if we have the expected minimum tools
    expected_utility_tools = [
        "search_project_history",
        "count_project_tokens",
        "list_sessions",
        "describe_session",
    ]

    # Also check for critical model tools that should always be available
    expected_model_tools = [
        "chat_with_gemini25_pro",
        "chat_with_gemini25_flash",
        "chat_with_o3",
    ]

    has_utility_tools = all(
        tool_id in TOOL_REGISTRY for tool_id in expected_utility_tools
    )
    has_model_tools = any(
        tool_id in TOOL_REGISTRY for tool_id in expected_model_tools
    )  # At least one model tool

    if not TOOL_REGISTRY or not has_utility_tools:
        # Force re-import to re-register utility tools
        import sys

        # Remove from cache to force re-registration
        sys.modules.pop("mcp_the_force.tools.definitions", None)
        sys.modules.pop("mcp_the_force.tools.search_history", None)
        sys.modules.pop("mcp_the_force.tools.count_project_tokens", None)
        sys.modules.pop("mcp_the_force.tools.list_sessions", None)
        sys.modules.pop("mcp_the_force.tools.describe_session", None)

        # Importing this module registers every tool class via the @tool decorator
        from . import definitions  # noqa: F401

    # Always try to load autogen if not loaded or if we don't have model tools
    if not _autogen_loaded or not has_model_tools:
        logger.debug(
            f"Loading autogen: _autogen_loaded={_autogen_loaded}, has_model_tools={has_model_tools}"
        )

        # Force re-import of autogen if model tools are missing
        if not has_model_tools:
            import sys

            sys.modules.pop("mcp_the_force.tools.autogen", None)
            logger.debug("Forcing autogen re-import due to missing model tools")

        # Import autogen to generate dynamic tools
        from . import autogen  # noqa: F401

        _autogen_loaded = True


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
    requires_capability: Callable[[Any], bool] | None = None


@dataclass
class ToolMetadata:
    """Metadata about a registered tool."""

    id: str
    spec_class: Type[ToolSpec]
    parameters: Dict[str, ParameterInfo]
    model_config: Dict[str, Any]
    aliases: List[str] = field(default_factory=list)
    capabilities: Optional[AdapterCapabilities] = None


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
                requires_capability=param_info.get("requires_capability"),
            )

        # Create metadata
        metadata = ToolMetadata(
            id=tool_id,
            spec_class=cls,
            parameters=parameters,
            model_config=model_config,
            aliases=aliases or [],
            capabilities=None,  # Will be set during blueprint processing
        )

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
        cls._tool_metadata = metadata

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
