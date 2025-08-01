"""Tools module for dataclass-based tool definitions."""

# Import core components first
from .descriptors import Route
from .base import ToolSpec
from .registry import tool

# Static tool definitions imported lazily to avoid circular imports

# Import service registrations
from . import local_service  # noqa: F401

# Autogen is now imported lazily by registry._ensure_populated() to avoid circular imports

__all__ = ["Route", "ToolSpec", "tool"]
