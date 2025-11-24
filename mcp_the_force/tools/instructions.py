"""Tool to retrieve a concise operator guide for using The Force."""

from .base import ToolSpec
from .registry import tool
from ..local_services.instructions_service import InstructionsService
from .descriptors import Route


@tool
class GetInstructionsTool(ToolSpec):
    """Return a detailed guide for LLM agents on how to use The Force MCP server."""

    model_name = "get_instructions"
    adapter_class = None  # local service, no provider call
    description = "Get a comprehensive usage guide for The Force, including context, sessions, and async jobs."
    timeout = 15
    service_cls = InstructionsService

    include_async: bool = Route.prompt(  # type: ignore[assignment]
        default=False,
        description="If true, highlight async job usage tips in the guide.",
    )
    guide_path: str = Route.prompt(  # type: ignore[assignment]
        default="docs/INSTRUCTIONS.md",
        description="Path to the markdown guide; relative paths are resolved from the server CWD.",
    )
