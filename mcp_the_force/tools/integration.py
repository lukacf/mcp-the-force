"""Integration layer between dataclass tools and FastMCP."""

from typing import Any, Dict, List, Optional, get_origin, get_args, Union, Annotated
from inspect import Parameter, Signature
from fastmcp import FastMCP, Context
import fastmcp.exceptions
import logging
from pydantic import Field
from .registry import list_tools, ToolMetadata
from .executor import executor
from .naming import sanitize_tool_name
from ..utils.scope_manager import scope_manager
from ..logging.setup import get_instance_id

logger = logging.getLogger(__name__)


def create_tool_function(metadata: ToolMetadata):
    """Create a function with proper signature for FastMCP registration."""

    # Build parameter list for signature
    sig_params: List[Parameter] = []

    # Get parameters sorted by position (positional first, then keyword-only)
    params_list = list(metadata.parameters.values())
    params_list.sort(key=lambda p: (p.position is None, p.position or 0))

    for param in params_list:
        # Check if parameter has capability requirements
        if param.requires_capability and metadata.capabilities:
            try:
                # Check if the model supports this parameter
                if not param.requires_capability(metadata.capabilities):
                    # Skip this parameter - not supported by model
                    logger.debug(
                        f"Skipping parameter {param.name} for {metadata.id} - not supported by model"
                    )
                    continue
            except Exception as e:
                # If capability check fails, skip the parameter
                logger.debug(
                    f"Capability check failed for {param.name} in {metadata.id}: {e}, skipping"
                )
                continue

        # Determine parameter kind
        param_kind = (
            Parameter.POSITIONAL_OR_KEYWORD
            if param.position is not None
            else Parameter.KEYWORD_ONLY
        )

        # Determine default value
        if param.required:
            default = Parameter.empty
        else:
            default = param.default

        # Create parameter with description if available
        param_type = param.type
        if param.description:
            # Use Annotated type with pydantic Field to include description
            annotated_type: Any = Annotated[
                param_type, Field(description=param.description)
            ]
        else:
            annotated_type = param_type

        sig_params.append(
            Parameter(
                name=param.name,
                kind=param_kind,
                default=default,
                annotation=annotated_type,
            )
        )

    # Add FastMCP Context as the LAST parameter AFTER all keyword-only params
    # Separate positional/keyword params from keyword-only params  
    positional_params = [p for p in sig_params if p.kind != Parameter.KEYWORD_ONLY]
    keyword_only_params = [p for p in sig_params if p.kind == Parameter.KEYWORD_ONLY]
    
    # Add Context before keyword-only params
    context_param = Parameter(
        name="ctx",
        kind=Parameter.POSITIONAL_OR_KEYWORD,
        default=None,
        annotation=Context,
    )
    
    # Rebuild params in correct order: positional, ctx, then keyword-only
    ordered_params = positional_params + [context_param] + keyword_only_params

    # Create signature with correct parameter order
    signature = Signature(ordered_params, return_annotation=str)

    # Create the actual function that can handle positional args
    async def tool_function(*args, **kwargs) -> str:
        """Dynamic tool function."""
        # Bind positional and keyword arguments to the signature
        try:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            
            # Extract ctx and remove it from arguments so downstream validation doesn't see it
            ctx = bound.arguments.pop("ctx", None)
            if ctx is not None:
                logger.warning("[CHATTER-DEBUG] ✅ Context extracted in integration layer")
            else:
                logger.warning("[CHATTER-DEBUG] ❌ No Context in integration layer")

            # Decide what we want to use as the scope id.
            # 1. Prefer an explicit session_id if the caller supplied one
            # 2. Otherwise fall back to the instance_id set by setup_logging()
            scope_id: Optional[str] = (
                bound.arguments.get("session_id") or get_instance_id()
            )

            # Debug logging
            logger.debug(
                f"[INTEGRATION] Tool {metadata.id} - session_id: {bound.arguments.get('session_id')}, instance_id: {get_instance_id()}, final scope_id: {scope_id}"
            )

            # If we have an instance_id, prepend "instance_" to distinguish from session IDs
            if scope_id and not bound.arguments.get("session_id"):
                scope_id = f"instance_{scope_id}"
                logger.debug(f"[INTEGRATION] Using instance-based scope: {scope_id}")

            # Make the whole execution run inside that scope
            async with scope_manager.scope(scope_id):
                # IMPORTANT: pass ctx to executor.execute as a privileged kwarg
                result = await executor.execute(metadata, ctx=ctx, **bound.arguments)
                logger.info(
                    f"[INTEGRATION] Tool {metadata.id} completed, returning result"
                )
                return result
        except TypeError as e:
            # Provide helpful error message via MCP error mechanism
            raise fastmcp.exceptions.ToolError(f"Invalid arguments: {e}")

    # Set metadata
    tool_function.__name__ = metadata.id
    tool_function.__doc__ = metadata.model_config["description"]
    # Set signature using setattr to avoid mypy complaints
    setattr(tool_function, "__signature__", signature)

    # CRITICAL: Set annotations for FastMCP 2.x compatibility
    # FastMCP uses pydantic which expects __annotations__ to be set
    annotations: Dict[str, Any] = {"return": str}
    annotations["ctx"] = Context  # so FastMCP recognizes it

    for sig_param in sig_params:
        # Get the actual type from the parameter's annotation
        # If it's Annotated, we need to extract the actual type
        if get_origin(sig_param.annotation) is Annotated:
            # Get the actual type from Annotated[type, description]
            actual_type = get_args(sig_param.annotation)[0]
        else:
            actual_type = sig_param.annotation

        # Check the actual type for special handling
        is_bool_type = False
        is_float_type = False
        is_dict_type = False
        is_list_str_type = False
        is_int_type = False
        origin = get_origin(actual_type)

        if origin is Union:  # Handles Optional[bool], Optional[float], etc.
            args = get_args(actual_type)
            if bool in args:
                is_bool_type = True
            elif float in args:
                is_float_type = True
            elif int in args:
                is_int_type = True
            # Check for Dict or List in Optional
            for arg in args:
                if get_origin(arg) is dict:
                    is_dict_type = True
                elif get_origin(arg) is list:
                    list_args = get_args(arg)
                    if list_args and list_args[0] is str:
                        is_list_str_type = True
        elif actual_type is bool:
            is_bool_type = True
        elif actual_type is float:
            is_float_type = True
        elif actual_type is int:
            is_int_type = True
        elif origin is dict:
            is_dict_type = True
        elif origin is list:
            # Direct List[str]
            list_args = get_args(actual_type)
            if list_args and list_args[0] is str:
                is_list_str_type = True

        if is_bool_type or is_float_type or is_dict_type or is_int_type:
            # If it's a boolean, float, int, or dict, tell FastMCP to expect Optional[str]
            # This allows string values "true"/"false", numeric strings like "0.5" or "123",
            # or JSON strings like '{"key": "value"}' to pass Pydantic validation.
            # Our internal ParameterValidator will then correctly coerce the string to the expected type.

            # If original annotation had a Field description, preserve it
            if get_origin(sig_param.annotation) is Annotated:
                # Extract the Field metadata from the Annotated type
                args = get_args(sig_param.annotation)
                if len(args) > 1 and hasattr(args[1], "description"):
                    # Preserve the Field with description
                    annotations[sig_param.name] = Annotated[Optional[str], args[1]]
                else:
                    annotations[sig_param.name] = Optional[str]
            else:
                annotations[sig_param.name] = Optional[str]
        elif is_list_str_type:
            # Accept either a real array or a JSON string.
            # Pydantic will validate Union[List[str], str, None], and our
            # ParameterValidator will coerce strings like "[\"a\"]" to List[str].
            from typing import (
                Union as _Union,
                Optional as _Optional,
                List as _List,
                Annotated as _Annotated,
            )

            # Detect Optional[List[str]] vs List[str]
            is_optional_list = get_origin(actual_type) is Union and type(
                None
            ) in get_args(actual_type)
            base_union = _Union[_List[str], str]
            accepts_type = _Optional[base_union] if is_optional_list else base_union

            if get_origin(sig_param.annotation) is Annotated:
                # Preserve Field(description=...)
                args = get_args(sig_param.annotation)
                if len(args) > 1 and hasattr(args[1], "description"):
                    annotations[sig_param.name] = _Annotated[accepts_type, args[1]]
                else:
                    annotations[sig_param.name] = accepts_type
            else:
                annotations[sig_param.name] = accepts_type
        else:
            # For all other types, use the annotation (which may include description)
            annotations[sig_param.name] = sig_param.annotation

    tool_function.__annotations__ = annotations

    return tool_function


def register_all_tools(mcp: FastMCP) -> None:
    """Register all tools with FastMCP server."""
    tools = list_tools()

    for tool_id, metadata in tools.items():
        try:
            # Skip aliases (they share the same metadata object)
            if tool_id != metadata.id:
                continue

            # Create function with proper signature
            tool_func = create_tool_function(metadata)

            # Sanitize tool name for MCP compliance
            safe_tool_id = sanitize_tool_name(tool_id)

            # Register with FastMCP under sanitized primary name
            mcp.tool(name=safe_tool_id)(tool_func)
            logger.debug(
                f"Registered tool with FastMCP: {safe_tool_id} (from {tool_id})"
            )

            # Register aliases with sanitization
            for alias in metadata.aliases:
                safe_alias = sanitize_tool_name(alias)
                mcp.tool(name=safe_alias)(tool_func)
                logger.debug(
                    f"Registered alias: {safe_alias} -> {safe_tool_id} (from {alias} -> {tool_id})"
                )

        except Exception as e:
            logger.error(f"Failed to register tool {tool_id}: {e}")

    # Conditionally register developer tools
    _register_developer_tools(mcp)


def _register_developer_tools(mcp: FastMCP) -> None:
    """Register developer-mode tools if enabled."""
    from ..config import get_settings

    settings = get_settings()
    if settings.logging.developer_mode.enabled:
        try:
            # Import logging tools to trigger @tool registration
            from . import logging_tools  # noqa: F401
            from .registry import get_tool

            # Register the logging tool with FastMCP
            metadata = get_tool("search_mcp_debug_logs")
            if metadata:
                tool_func = create_tool_function(metadata)
                mcp.tool(name="search_mcp_debug_logs")(tool_func)
                logger.debug("Registered developer tool: search_mcp_debug_logs")
            else:
                logger.error("Could not find search_mcp_debug_logs tool in registry")
        except ImportError as e:
            logger.warning(f"Could not import logging tools: {e}")
        except Exception as e:
            logger.error(f"Failed to register developer tools: {e}")


def create_vector_store_tool(mcp: FastMCP) -> None:
    """Create the vector store management tool."""

    @mcp.tool()
    async def create_vector_store_tool(
        files: Annotated[
            List[str],
            Field(description="List of file paths to include in the vector store"),
        ],
        name: Annotated[
            Optional[str], Field(description="Optional name for the vector store")
        ] = None,
    ) -> Dict[str, str]:
        """Create a vector store from files and return its ID.

        Args:
            files: List of file paths to include in the vector store
            name: Optional name for the vector store

        Returns:
            Dictionary with vector_store_id
        """
        try:
            from ..vectorstores.manager import vector_store_manager

            result = await vector_store_manager.create(files)
            if result:
                # Handle both old string return and new dict return
                if isinstance(result, dict):
                    return {
                        "vector_store_id": result.get("store_id", ""),
                        "status": "created",
                    }
                else:
                    # Legacy string return
                    return {"vector_store_id": result, "status": "created"}
            else:
                return {"vector_store_id": "", "status": "no_supported_files"}
        except Exception as e:
            logger.error(f"Error creating vector store: {e}")
            return {"vector_store_id": "", "status": "error", "error": str(e)}
