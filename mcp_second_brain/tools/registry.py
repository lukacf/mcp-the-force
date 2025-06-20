"""Tool registry and decorator for automatic tool registration."""
from typing import Type, Dict, Any, Callable, TypeVar
from dataclasses import dataclass
import inspect
import logging
from .base import ToolSpec
from .descriptors import RouteDescriptor

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=ToolSpec)

# Global registry of all tools
TOOL_REGISTRY: Dict[str, 'ToolMetadata'] = {}


@dataclass
class ParameterInfo:
    """Information about a tool parameter."""
    name: str
    type: Type
    type_str: str
    route: str
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


def tool(cls: Type[T]) -> Type[T]:
    """Decorator that registers a tool specification.
    
    Usage:
        @tool
        class MyTool(ToolSpec):
            model_name = "my-model"
            instructions: str = Route.prompt(pos=0)
    """
    if not issubclass(cls, ToolSpec):
        raise TypeError(f"{cls.__name__} must inherit from ToolSpec")
    
    # Extract tool ID from class name (convert CamelCase to snake_case)
    tool_id = _camel_to_snake(cls.__name__)
    
    # Get model configuration
    model_config = cls.get_model_config()
    if not model_config["model_name"]:
        raise ValueError(f"{cls.__name__} must define model_name")
    if not model_config["adapter_class"]:
        raise ValueError(f"{cls.__name__} must define adapter_class")
    
    # Extract parameters
    parameters = {}
    positions_used = {}
    
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
            description=param_info["description"]
        )
    
    # Create metadata
    metadata = ToolMetadata(
        id=tool_id,
        spec_class=cls,
        parameters=parameters,
        model_config=model_config
    )
    
    # Register the tool
    TOOL_REGISTRY[tool_id] = metadata
    logger.info(f"Registered tool: {tool_id}")
    
    # Store metadata on the class for easy access
    cls._tool_metadata = metadata
    
    return cls


def get_tool(tool_id: str) -> ToolMetadata | None:
    """Get tool metadata by ID."""
    return TOOL_REGISTRY.get(tool_id)


def list_tools() -> Dict[str, ToolMetadata]:
    """Get all registered tools."""
    return TOOL_REGISTRY.copy()


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            # Add underscore before uppercase letter if:
            # - Previous char is lowercase
            # - Or next char is lowercase (handles acronyms)
            if (name[i-1].islower() or 
                (i < len(name) - 1 and name[i+1].islower())):
                result.append('_')
        result.append(char.lower())
    return ''.join(result)