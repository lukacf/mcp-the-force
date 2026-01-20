"""Tool definitions for utility and special-purpose tools.

All AI model chat/research tools are now auto-generated in autogen.py.
This file contains only utility tools and imports.
"""

from __future__ import annotations

# Import tools to ensure registration
from . import search_history  # noqa: F401
from . import count_project_tokens  # noqa: F401
from . import list_sessions  # noqa: F401
from . import describe_session  # noqa: F401
from . import group_think  # noqa: F401
from . import async_jobs  # noqa: F401
from . import instructions  # noqa: F401
from . import work_with  # noqa: F401
from . import consult_with  # noqa: F401
# Note: search_attachments is not imported here to prevent MCP exposure
# It remains available for internal model function calling
# Note: logging_tools is imported conditionally in integration.py when developer mode is enabled
