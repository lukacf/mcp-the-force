"""Tool for describing/summarizing AI sessions."""

from typing import Optional
from .base import ToolSpec
from .descriptors import Route
from .registry import tool
from ..local_services.describe_session import DescribeSessionService
from ..config import get_settings


@tool
class DescribeSession(ToolSpec):
    """Generate an AI-powered summary of an existing session.

    This tool analyzes the conversation history of a specified session
    and produces a concise summary using AI. Summaries are cached to
    avoid redundant generation.
    """

    # Local service configuration
    model_name = "describe_session"
    description = (
        "Generate an AI-powered summary of an existing session's conversation history. "
        "Uses another AI model to analyze and summarize the conversation. "
        "Summaries are cached to avoid redundant generation."
    )
    service_cls = DescribeSessionService
    adapter_class = None  # Local service, no adapter needed
    timeout = 300  # 5 minutes - summarization can take time

    # Tool parameters
    session_id: str = Route.adapter(description="The ID of the session to summarize")  # type: ignore[assignment]

    summarization_model: Optional[str] = Route.adapter(  # type: ignore[assignment]
        default_factory=lambda: get_settings().tools.default_summarization_model,
        description="The AI model to use for generating the summary. Defaults to the configured default summarization model.",
    )

    extra_instructions: Optional[str] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description="Additional instructions for the AI when generating the summary (e.g., 'Focus on technical decisions', 'Highlight action items')",
    )
