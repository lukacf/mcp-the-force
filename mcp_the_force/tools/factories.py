"""Factory functions for generating tool classes."""

from typing import Dict, Any, Type
from .base import ToolSpec
from .registry import tool
from .blueprint import ToolBlueprint
from .descriptors import RouteDescriptor


def make_tool(blueprint: ToolBlueprint) -> Type[ToolSpec]:
    """Route to appropriate factory based on tool type."""
    if blueprint.tool_type == "chat":
        return make_chat_tool(blueprint)
    elif blueprint.tool_type == "research":
        return make_research_tool(blueprint)
    else:
        raise ValueError(f"Unknown tool type: {blueprint.tool_type}")


def make_chat_tool(bp: ToolBlueprint) -> Type[ToolSpec]:
    """Generate a chat tool class from blueprint."""
    attrs: Dict[str, Any] = {
        "__doc__": f"{bp.description}\n\nAuto-generated chat tool.",
        "__module__": "mcp_the_force.tools.autogen",  # Set proper module
        "model_name": bp.model_name,
        "adapter_class": bp.adapter_key,
        "context_window": bp.context_window,
        "timeout": bp.timeout,
    }

    # Copy Route descriptors AND type annotations from param class and all parent classes
    # We need to walk the MRO to get descriptors from BaseToolParams too

    # First, collect all annotations in MRO order
    all_annotations = {}
    for cls in reversed(bp.param_class.__mro__):
        if cls is object:  # Skip object base class
            continue
        if hasattr(cls, "__annotations__"):
            all_annotations.update(cls.__annotations__)

    # Set annotations on the generated class
    attrs["__annotations__"] = all_annotations

    # Then copy Route descriptors
    for cls in bp.param_class.__mro__:
        if cls is object:  # Skip object base class
            continue
        for name, value in cls.__dict__.items():
            # Check if it's a RouteDescriptor
            if isinstance(value, RouteDescriptor):
                # Don't override if already defined by a subclass
                if name not in attrs:
                    attrs[name] = value

    # Generate class name (e.g., ChatWithGPT4_1)
    # Clean up model name for valid Python identifier
    clean_model_name = (
        bp.model_name.replace("-", "_").replace(".", "_").replace(" ", "_")
    )
    # Convert to title case but preserve existing uppercase
    parts = clean_model_name.split("_")
    formatted_parts = []
    for part in parts:
        if part.isupper():  # Keep fully uppercase parts (like GPT)
            formatted_parts.append(part)
        else:
            formatted_parts.append(part.title())

    class_name = f"ChatWith{''.join(formatted_parts)}"

    # Create and register the class
    cls = type(class_name, (ToolSpec,), attrs)
    return tool(cls)


def make_research_tool(bp: ToolBlueprint) -> Type[ToolSpec]:
    """Generate a research tool class from blueprint."""
    attrs: Dict[str, Any] = {
        "__doc__": f"{bp.description}\n\nAuto-generated research tool.",
        "__module__": "mcp_the_force.tools.autogen",  # Set proper module
        "model_name": bp.model_name,
        "adapter_class": bp.adapter_key,
        "context_window": bp.context_window,
        "timeout": bp.timeout,
    }

    # Copy Route descriptors AND type annotations from param class and all parent classes
    # We need to walk the MRO to get descriptors from BaseToolParams too

    # First, collect all annotations in MRO order
    all_annotations = {}
    for cls in reversed(bp.param_class.__mro__):
        if cls is object:  # Skip object base class
            continue
        if hasattr(cls, "__annotations__"):
            all_annotations.update(cls.__annotations__)

    # Set annotations on the generated class
    attrs["__annotations__"] = all_annotations

    # Then copy Route descriptors
    for cls in bp.param_class.__mro__:
        if cls is object:  # Skip object base class
            continue
        for name, value in cls.__dict__.items():
            # Check if it's a RouteDescriptor
            if isinstance(value, RouteDescriptor):
                # Don't override if already defined by a subclass
                if name not in attrs:
                    attrs[name] = value

    # Generate class name (e.g., ResearchWithO3DeepResearch)
    clean_model_name = (
        bp.model_name.replace("-", "_").replace(".", "_").replace(" ", "_")
    )
    parts = clean_model_name.split("_")
    formatted_parts = []
    for part in parts:
        if part.isupper():
            formatted_parts.append(part)
        else:
            formatted_parts.append(part.title())

    class_name = f"ResearchWith{''.join(formatted_parts)}"

    # Create and register the class
    cls = type(class_name, (ToolSpec,), attrs)
    return tool(cls)
