"""Tools module for dataclass-based tool definitions."""

# Generate dynamic tools first
from . import autogen  # noqa: F401

# Import core components
from .descriptors import Route
from .base import ToolSpec
from .registry import tool

# Import static tool definitions
from . import definitions  # noqa: F401

# Import service registrations
from . import local_service  # noqa: F401
from . import logging_service  # noqa: F401

__all__ = ["Route", "ToolSpec", "tool"]
