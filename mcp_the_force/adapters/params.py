"""Base parameter definition for all adapters.

This module defines the base parameter class that all adapter-specific
parameter classes inherit from. Each adapter defines its own parameter
class in its definitions.py file.

The inheritance pattern ensures that all tools have a consistent base
set of parameters while allowing adapter-specific extensions.
"""

from typing import List

# Import Route directly for base parameters
from ..tools.descriptors import Route


class BaseToolParams:
    """Base parameters that every tool has.

    This is not a dataclass - it works with Route descriptors like ToolSpec.
    The protocol-based adapters will receive instances with these attributes
    populated from the Route descriptors.

    All adapter-specific parameter classes should inherit from this base class
    and add their own parameters with appropriate capability requirements.
    """

    instructions: str = Route.prompt(pos=0, description="User instructions")
    output_format: str = Route.prompt(pos=1, description="Expected output format")
    context: List[str] = Route.prompt(pos=2, description="Context files/directories")
    session_id: str = Route.session(description="Session ID for conversation")
    disable_memory_store: bool = Route.adapter(
        default=False,
        description="Disable saving the conversation to project history",
    )
