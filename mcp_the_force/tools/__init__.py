"""Tools module for dataclass-based tool definitions."""

from .descriptors import Route
from .base import ToolSpec
from .registry import tool

__all__ = ["Route", "ToolSpec", "tool"]
