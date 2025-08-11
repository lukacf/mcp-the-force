"""Base parameter definition for all adapters.

This module defines the base parameter class that all adapter-specific
parameter classes inherit from. Each adapter defines its own parameter
class in its definitions.py file.

The inheritance pattern ensures that all tools have a consistent base
set of parameters while allowing adapter-specific extensions.
"""

from typing import List, Optional

# Import Route directly for base parameters
from ..tools.descriptors import Route
from .param_model import ParamModel


class BaseToolParams(ParamModel):
    """Base parameters that every tool has.

    This is not a dataclass - it works with Route descriptors like ToolSpec.
    The protocol-based adapters will receive instances with these attributes
    populated from the Route descriptors.

    All adapter-specific parameter classes should inherit from this base class
    and add their own parameters with appropriate capability requirements.

    IMPORTANT: The type annotations (e.g., `str`, `List[str]`) are REQUIRED
    for runtime introspection via get_type_hints(). Thanks to the @dataclass_transform
    decorator on ParamModel, type checkers understand that Route descriptors
    will provide the annotated types at runtime.
    """

    instructions: str = Route.prompt(  # type: ignore[assignment]
        pos=0,
        description=(
            "(Required) The primary directive for the AI model. This is the main input that drives "
            "the model's generation process. Should clearly and concisely state the task to be performed. "
            "Syntax: A natural language string detailing the task. "
            "Example: 'Refactor the attached Python code to improve performance and add error handling.'"
        ),
    )
    output_format: str = Route.prompt(  # type: ignore[assignment]
        pos=1,
        description=(
            "(Required) A description of the desired format for the model's response. "
            "Guides the model in structuring its output. Can be as simple as 'plain text' or as complex as "
            "'A markdown report with sections for analysis, recommendations, and code examples.' "
            "For JSON output, use the structured_output_schema parameter instead for better validation. "
            "Syntax: A natural language string. "
            "Example: 'A bulleted list of key findings.'"
        ),
    )
    context: Optional[List[str]] = Route.prompt(  # type: ignore[assignment]
        pos=2,
        description=(
            "(Optional) A list of file or directory paths to be used as context for the AI model. "
            "The content of these files is made available to the model, either directly in the prompt "
            "(for smaller files) or via a searchable vector store (for larger files). The system "
            "automatically handles this split based on the model's context window size. "
            "Syntax: An array of strings (not a JSON string). Do not wrap the array in quotes. "
            "Each string must be an absolute path. "
            'PREFERRED FORMAT: ["/path/to/project/main.py", "/path/to/project/utils/"] '
            'NOT: "["/path/to/project/main.py", "/path/to/project/utils/"]"'
        ),
        default_factory=list,
    )
    priority_context: Optional[List[str]] = Route.prompt(  # type: ignore[assignment]
        pos=3,
        description=(
            "(Optional) A list of file or directory paths that should be prioritized for inline inclusion "
            "in the prompt, even if they would normally overflow to the vector store. Ensures critical "
            "files are always directly in the model's context window, as long as they fit within the "
            "total token budget. Files in priority_context are processed before files in context. "
            "Syntax: An array of strings (not a JSON string). Do not wrap the array in quotes. "
            "Each string must be an absolute path. "
            'PREFERRED FORMAT: ["/path/to/project/critical_config.yaml"] '
            'NOT: "["/path/to/project/critical_config.yaml"]"'
        ),
        default_factory=list,
    )
    session_id: str = Route.session(  # type: ignore[assignment, misc]
        description=(
            "(Required) A unique identifier for a multi-turn conversation. CRITICAL: Reuse the same session_id "
            "to continue an existing conversation - the AI model will remember previous exchanges and context. "
            "Creating a NEW session_id starts a completely blank conversation where the AI has no memory of "
            "previous interactions. Always reuse existing session_id unless you specifically want to start fresh. "
            "All models (OpenAI, Gemini, Grok) support session continuity. Sessions are permanently stored. "
            "Use descriptive IDs like 'project-analysis-2024' and reuse them for related conversations. "
            "TIP: Use 'list_sessions' tool to see existing sessions and their IDs. "
            "WARNING: New session_id = AI forgets everything from previous calls. "
            "Example: 'debug-auth-issue-2024-07-16' (reuse this same ID for follow-ups)"
        )
    )
    disable_history_record: bool = Route.adapter(  # type: ignore[assignment]
        default=False,
        description=(
            "(Optional) If true, prevents the current conversation turn from being saved to the long-term "
            "project history vector store. Useful for ephemeral or sensitive queries that should not be "
            "part of the project's institutional memory. This does not affect the short-term session "
            "history managed by session_id. "
            "Syntax: A boolean (true or false). "
            "Default: false"
        ),
    )
