"""consult_with tool specification.

Routes consultations to internal chat_with_* API tools.
"""

from .base import ToolSpec
from .descriptors import Route
from .registry import tool
from ..local_services.cli_agent_service import ConsultationService


@tool
class ConsultWith(ToolSpec):
    """Quick advisory: ask a model for opinions/analysis without file access."""

    model_name = "consult_with"
    description = (
        "**ONLY use when user EXPLICITLY says 'consult with [model]' or 'ask [model]'** - "
        "Calls an API model for quick questions or advice. NO file access, NO tools - just conversation. "
        "DEFAULT TO work_with for all other cases. If user says 'work with X' use work_with, not this."
    )

    # Use local service instead of adapter
    service_cls = ConsultationService
    adapter_class = None  # Signal to executor that this runs locally
    timeout = 120  # 2 minute timeout for API calls

    # Parameters
    model: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) The API model to consult. "
            "Options: 'gpt-5.2', 'gpt-5.2-pro', 'gemini-3-pro-preview', 'gemini-3-flash-preview', "
            "'grok-4.1', 'claude-opus-4-5', 'claude-sonnet-4-5', etc. "
            "Routes to the corresponding chat_with_* tool internally."
        )
    )

    question: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) The question or prompt for the model. "
            "Be specific about what information or analysis you need."
        )
    )

    session_id: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) A unique identifier for the conversation session. "
            "Reuse the same session_id to continue a multi-turn conversation."
        )
    )

    output_format: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) Desired format for the response. "
            "Examples: 'plain text', 'markdown', 'JSON', 'code only'"
        )
    )
