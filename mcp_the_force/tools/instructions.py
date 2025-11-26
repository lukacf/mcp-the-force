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


@tool
class ListGuidesTool(ToolSpec):
    """List available Force guides (URIs and titles) for quick reference."""

    model_name = "list_force_guides"
    adapter_class = "local"
    description = "List built-in Force guides (usage, async jobs, group think) with URIs you can pass to read_force_guide."
    timeout = 15
    verbose: bool = Route.prompt(  # type: ignore[assignment]
        default=False,
        description="When true, include one-line summaries with each guide.",
    )

    def run(self, verbose: bool = False) -> dict:  # type: ignore[override]
        guides = [
            {"uri": "force://guides/usage", "title": "Usage Guide (full)"},
            {"uri": "force://guides/async", "title": "Async Jobs Quickstart"},
            {"uri": "force://guides/groupthink", "title": "GroupThink Quickstart"},
        ]
        if verbose:
            guides[0]["summary"] = (
                "How to use chat_with_*, context, sessions, priority_context."
            )
            guides[1]["summary"] = (
                "When to use start_job/poll_job/cancel_job and patterns."
            )
            guides[2]["summary"] = (
                "How to run collaborative panels, sessions, and synthesis."
            )
        return {"guides": guides}


@tool
class ReadGuideTool(ToolSpec):
    """Read a specific Force guide by URI or path."""

    model_name = "read_force_guide"
    adapter_class = None
    description = "Read a Force guide by URI (force://guides/usage|async|groupthink) or by explicit path."
    timeout = 15
    service_cls = InstructionsService

    guide_path: str = Route.prompt(  # type: ignore[assignment]
        default="force://guides/usage",
        description="Guide URI or path. Use force://guides/usage, force://guides/async, force://guides/groupthink, or a file path.",
    )
    include_async: bool = Route.prompt(  # type: ignore[assignment]
        default=True,
        description="If true, append async job tips to the guide output.",
    )
