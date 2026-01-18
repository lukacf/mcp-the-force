"""consult_with tool specification.

Routes consultations to internal chat_with_* API tools.
"""

from .base import ToolSpec
from .descriptors import Route
from .registry import tool
from ..local_services.cli_agent_service import ConsultationService


@tool
class ConsultWith(ToolSpec):
    """Consult with an API model for quick questions and analysis."""

    model_name = "consult_with"
    description = (
        "Consult with an API model for quick questions, analysis, or advice. "
        "Routes to internal chat_with_* tools based on the model parameter. "
        "Supports session continuity for multi-turn conversations."
    )

    # Use local service instead of adapter
    service_cls = ConsultationService
    adapter_class = None  # Signal to executor that this runs locally
    timeout = 120  # 2 minute timeout for API calls

    # Parameters
    model: str = Route.prompt(  # type: ignore[assignment]
        description=(
            "(Required) The API model to consult. "
            "Options: 'gpt52', 'gpt52_pro', 'gemini3_pro', 'gemini3_flash', 'grok41', etc. "
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
