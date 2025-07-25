"""Central registry for tool blueprints."""

from typing import List
from .blueprint import ToolBlueprint

BLUEPRINTS: List[ToolBlueprint] = []


def register_blueprints(bps: List[ToolBlueprint]) -> None:
    """Register blueprints from adapters."""
    BLUEPRINTS.extend(bps)


def clear_blueprints() -> None:
    """Clear all registered blueprints (useful for testing)."""
    BLUEPRINTS.clear()


def get_blueprints() -> List[ToolBlueprint]:
    """Get all registered blueprints."""
    return BLUEPRINTS.copy()
