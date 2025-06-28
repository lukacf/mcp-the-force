"""Integration layer between dataclass tools and FastMCP."""

from typing import Any, Dict, List, Optional
from inspect import Parameter, Signature
from mcp.server.fastmcp import FastMCP
import fastmcp.exceptions
import logging
from .registry import list_tools, ToolMetadata
from .executor import executor

logger = logging.getLogger(__name__)


def create_tool_function(metadata: ToolMetadata):
    """Create a function with proper signature for FastMCP registration."""

    # Build parameter list for signature
    sig_params = []

    # Get parameters sorted by position (positional first, then keyword-only)
    params_list = list(metadata.parameters.values())
    params_list.sort(key=lambda p: (p.position is None, p.position or 0))

    for param in params_list:
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

        # Create parameter
        sig_params.append(
            Parameter(
                name=param.name, kind=param_kind, default=default, annotation=param.type
            )
        )

    # Create signature
    signature = Signature(sig_params, return_annotation=str)

    # Create the actual function that can handle positional args
    async def tool_function(*args, **kwargs) -> str:
        """Dynamic tool function."""
        # Bind positional and keyword arguments to the signature
        try:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            return await executor.execute(metadata, **bound.arguments)
        except TypeError as e:
            # Provide helpful error message via MCP error mechanism
            raise fastmcp.exceptions.ToolError(f"Invalid arguments: {e}")

    # Set metadata
    tool_function.__name__ = metadata.id
    tool_function.__doc__ = metadata.model_config["description"]
    # Set signature using setattr to avoid mypy complaints
    setattr(tool_function, "__signature__", signature)

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

            # Register with FastMCP under primary name
            mcp.tool(name=tool_id)(tool_func)
            logger.info(f"Registered tool with FastMCP: {tool_id}")

            # Register aliases
            for alias in metadata.aliases:
                mcp.tool(name=alias)(tool_func)
                logger.info(f"Registered alias: {alias} -> {tool_id}")

        except Exception as e:
            logger.error(f"Failed to register tool {tool_id}: {e}")


def create_list_models_tool(mcp: FastMCP) -> None:
    """Create the list_models utility tool."""

    @mcp.tool()
    async def list_models() -> List[Dict[str, Any]]:
        """List all available AI models and their capabilities.

        Returns:
            List of model information including names, providers, and capabilities
        """
        models = []
        tools = list_tools()

        for tool_id, metadata in tools.items():
            # Skip aliases
            if (
                metadata.spec_class.__doc__
                and "Alias for" in metadata.spec_class.__doc__
            ):
                continue

            model_info = {
                "id": tool_id,
                "provider": metadata.model_config["adapter_class"],
                "model": metadata.model_config["model_name"],
                "context_window": metadata.model_config["context_window"],
                "timeout": metadata.model_config["timeout"],
                "description": metadata.model_config["description"],
                "parameters": [],
            }

            # Add parameter information
            for param_name, param_info in metadata.parameters.items():
                model_info["parameters"].append(
                    {
                        "name": param_name,
                        "type": param_info.type_str,
                        "required": param_info.required,
                        "route": param_info.route,
                        "description": param_info.description,
                    }
                )

            models.append(model_info)

        return models


def create_vector_store_tool(mcp: FastMCP) -> None:
    """Create the vector store management tool."""

    @mcp.tool()
    async def create_vector_store_tool(
        files: List[str], name: Optional[str] = None
    ) -> Dict[str, str]:
        """Create a vector store from files and return its ID.

        Args:
            files: List of file paths to include in the vector store
            name: Optional name for the vector store

        Returns:
            Dictionary with vector_store_id
        """
        try:
            from ..utils.vector_store import create_vector_store
            import asyncio

            vs_id = await asyncio.to_thread(create_vector_store, files)
            if vs_id:
                return {"vector_store_id": vs_id, "status": "created"}
            else:
                return {"vector_store_id": "", "status": "no_supported_files"}
        except Exception as e:
            logger.error(f"Error creating vector store: {e}")
            return {"vector_store_id": "", "status": "error", "error": str(e)}
