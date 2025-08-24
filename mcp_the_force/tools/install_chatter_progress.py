"""Install Chatter progress display components."""

from typing import Optional
from .base import ToolSpec
from .registry import tool
from .descriptors import Route
from ..local_services.chatter_progress_installer import ChatterProgressInstaller


@tool
class InstallChatterProgress(ToolSpec):
    """Install Chatter progress display components for real-time collaboration feedback."""

    model_name = "install_chatter_progress"
    description = (
        "Automatically install Chatter progress display components including status line scripts "
        "and hooks for real-time collaboration progress feedback in Claude Code. "
        "Safely merges with existing configurations without overwriting."
    )

    # This uses our ChatterProgressInstaller service
    service_cls = ChatterProgressInstaller
    adapter_class = None
    timeout = 30  # Installation should be quick

    action: str = Route.adapter(  # type: ignore[assignment]
        default="install",
        description=(
            "(Optional) Action to perform. "
            "'install' sets up progress display components, "
            "'uninstall' removes all Chatter components, "
            "'repair' re-installs with current detection, "
            "'status' shows current installation state. "
            "Syntax: A string, one of 'install', 'uninstall', 'repair', 'status'. "
            "Default: 'install'. "
            "Example: action='install'"
        ),
    )

    project_dir: Optional[str] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description=(
            "(Optional) Project directory for installation. "
            "If not specified, uses current MCP server project directory. "
            "Components will be installed in {project_dir}/.claude/ "
            "Syntax: A string path to project directory. "
            "Default: None (use current project). "
            "Example: project_dir='/path/to/my/project'"
        ),
    )

    with_hooks: bool = Route.adapter(  # type: ignore[assignment]
        default=True,
        description=(
            "(Optional) Whether to install lifecycle management hooks. "
            "Hooks provide automatic progress file initialization and cleanup. "
            "Set to false if you want status line only without hook integration. "
            "Syntax: A boolean (true or false). "
            "Default: true. "
            "Example: with_hooks=false"
        ),
    )

    dry_run: bool = Route.adapter(  # type: ignore[assignment]
        default=False,
        description=(
            "(Optional) Show what would be done without making any changes. "
            "Useful for previewing installation before applying. "
            "Syntax: A boolean (true or false). "
            "Default: false. "
            "Example: dry_run=true"
        ),
    )