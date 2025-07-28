"""Tool definitions for utility and special-purpose tools.

All AI model chat/research tools are now auto-generated in autogen.py.
This file contains only utility tools and imports.
"""

from __future__ import annotations

# Import tools to ensure registration
from . import search_history  # noqa: F401
# Note: search_attachments is not imported here to prevent MCP exposure
# It remains available for internal model function calling
# Note: logging_tools is imported conditionally in integration.py when developer mode is enabled
