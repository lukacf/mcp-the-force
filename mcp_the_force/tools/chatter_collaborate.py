"""Multi-model collaboration tool - Chatter."""

from typing import Optional, List
from .base import ToolSpec
from .registry import tool
from .descriptors import Route
from ..local_services.collaboration_service import CollaborationService


@tool
class ChatterCollaborate(ToolSpec):
    """Enable multiple AI models to collaborate on complex problems through structured multi-turn conversations."""

    model_name = "chatter_collaborate"
    description = (
        "Orchestrate multi-model collaborations where multiple AI models (GPT-5, Gemini 2.5 Pro, Claude, etc.) "
        "work together on complex problems through structured conversations. Models share a whiteboard vector store "
        "and can build on each other's ideas across multiple turns. Supports both round-robin and orchestrated modes."
    )

    # This uses our CollaborationService
    service_cls = CollaborationService
    adapter_class = None
    timeout = 3600  # 1 hour total for complete multi-turn collaboration

    session_id: str = Route.adapter(  # type: ignore[assignment]
        description=(
            "(Required) A unique identifier for the multi-turn collaboration session. "
            "CRITICAL: Reuse the same session_id to continue an existing collaboration - the service "
            "will remember previous exchanges and context. Creating a NEW session_id starts a completely "
            "blank collaboration where models have no memory of previous interactions. "
            "Use descriptive IDs like 'solve-authentication-bug-2024' and reuse them for follow-ups. "
            "TIP: Use 'list_sessions' tool to see existing collaboration sessions. "
            "WARNING: New session_id = models forget everything from previous collaboration turns. "
            "Example: 'debug-auth-issue-2024-07-16' (reuse this same ID for follow-ups)"
        ),
    )

    objective: str = Route.adapter(  # type: ignore[assignment]
        description=(
            "(Required) The main task or problem for models to solve collaboratively. "
            "This becomes the central focus that all participating models work toward. "
            "Should be clear, specific, and complex enough to benefit from multiple perspectives. "
            "Syntax: A natural language description of the problem. "
            "Example: 'Design and implement a robust authentication system with JWT tokens, "
            "refresh logic, and proper error handling for our REST API.'"
        ),
    )

    models: List[str] = Route.adapter(  # type: ignore[assignment]
        description=(
            "(Required) List of AI model tool names to participate in the collaboration. "
            "Models will take turns contributing to the discussion. Use a mix of different models "
            "for diverse perspectives (e.g., GPT-5 for reasoning, Gemini for code analysis, Claude for writing). "
            "Available models include: chat_with_gpt5, chat_with_gemini25_pro, chat_with_claude41_opus, "
            "chat_with_gpt5_mini, chat_with_gemini25_flash, chat_with_grok4, etc. "
            "Syntax: An array of strings (model tool names). "
            "Example: ['chat_with_gpt5', 'chat_with_gemini25_pro', 'chat_with_claude41_opus']"
        ),
    )

    user_input: str = Route.adapter(  # type: ignore[assignment]
        default="",
        description=(
            "(Optional) Additional input, guidance, or questions to add to the current collaboration turn. "
            "This gets added to the whiteboard for models to consider. Use this to steer the conversation, "
            "ask follow-up questions, or provide new requirements. Leave empty to let models continue "
            "their discussion without new input. "
            "Syntax: A natural language string. "
            "Default: '' (empty). "
            "Example: 'Please focus on security best practices and include error handling patterns.'"
        ),
    )

    mode: str = Route.adapter(  # type: ignore[assignment]
        default="round_robin",
        description=(
            "(Optional) Collaboration orchestration mode. 'round_robin' rotates through models in order, "
            "ensuring each gets equal participation. 'orchestrator' mode uses smart model selection "
            "(future enhancement - currently falls back to round_robin). "
            "Syntax: A string, one of 'round_robin' or 'orchestrator'. "
            "Default: 'round_robin'. "
            "Example: mode='round_robin'"
        ),
    )

    max_steps: int = Route.adapter(  # type: ignore[assignment]
        default=10,
        description=(
            "(Optional) Maximum number of collaboration turns before the session completes. "
            "Each step involves one model contributing to the discussion. Higher values allow "
            "for more thorough exploration but take longer. The collaboration can be resumed "
            "later if needed by calling with the same session_id. "
            "Syntax: An integer. "
            "Default: 10. "
            "Example: max_steps=15"
        ),
    )

    config: Optional[dict] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description=(
            "(Optional) Advanced configuration overrides for the collaboration. "
            "Can specify custom timeout_per_step, summarization_threshold, etc. "
            "Most users don't need this - the defaults work well. "
            "Syntax: A JSON object with configuration keys. "
            "Default: None (use system defaults). "
            "Example: {'timeout_per_step': 600, 'summarization_threshold': 100}"
        ),
    )