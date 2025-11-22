"""Multi-model collaboration tool - Chatter."""

from typing import Optional, List
from .base import ToolSpec
from .registry import tool
from .descriptors import Route
from ..local_services.collaboration_service import CollaborationService


@tool
class GroupThink(ToolSpec):
    """Enable multiple AI models to think together on complex problems through structured multi-turn conversations."""

    model_name = "group_think"
    description = (
        "Orchestrate group thinking sessions where multiple AI models (GPT-5, Gemini 2.5 Pro, Claude, etc.) "
        "collaborate on complex problems through structured conversations. Models share a whiteboard vector store "
        "and can build on each other's ideas across multiple turns. Provides comprehensive final reports. "
        "Supports both round-robin and orchestrated modes."
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
            "Available models include: chat_with_gpt51_codex, chat_with_gemini3_pro_preview, chat_with_claude41_opus, "
            "chat_with_gemini25_flash, chat_with_grok41, etc. "
            "Syntax: An array of strings (model tool names). "
            "Example: ['chat_with_gpt51_codex', 'chat_with_gemini3_pro_preview', 'chat_with_claude41_opus']"
        ),
    )

    output_format: str = Route.adapter(  # type: ignore[assignment]
        description=(
            "(Required) Specification of exactly what the group should produce and in what format. "
            "This is the only guidance the synthesis agent receives - be as detailed or general as needed. "
            "Examples: 'List of exactly 5 jokes with explanations', 'Complete Python implementation with docstrings and tests', "
            "'Technical design document with sections: Architecture, API Design, Database Schema, Deployment Guide'. "
            "The more specific, the more precisely the group will deliver what you want. "
            "Syntax: Clear specification of desired output format and content. "
            "Example: 'JSON object with keys: summary, recommendations, code_examples, next_steps'"
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

    context: Optional[List[str]] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description=(
            "(Optional) A list of file or directory paths to be used as context for the AI model. "
            "The content of these files is made available to the model, either directly in the prompt "
            "(for smaller files) or via a searchable vector store (for larger files). "
            "The system automatically handles this split based on the model's context window size. "
            "Syntax: An array of strings (not a JSON string). Do not wrap the array in quotes. "
            "Each string must be an absolute path. "
            'PREFERRED FORMAT: ["/path/to/project/main.py", "/path/to/project/utils/"] '
            'NOT: "["/path/to/project/main.py", "/path/to/project/utils/"]"'
        ),
    )

    priority_context: Optional[List[str]] = Route.adapter(  # type: ignore[assignment]
        default=None,
        description=(
            "(Optional) A list of file or directory paths that should be prioritized for inline "
            "inclusion in the prompt, even if they would normally overflow to the vector store. "
            "Ensures critical files are always directly in the model's context window, as long as "
            "they fit within the total token budget. Files in priority_context are processed before "
            "files in context. "
            "Syntax: An array of strings (not a JSON string). Do not wrap the array in quotes. "
            "Each string must be an absolute path. "
            'PREFERRED FORMAT: ["/path/to/project/critical_config.yaml"] '
            'NOT: "["/path/to/project/critical_config.yaml"]"'
        ),
    )

    discussion_turns: int = Route.adapter(  # type: ignore[assignment]
        default=6,
        description=(
            "(Optional) Number of turns for the discussion phase before synthesis. "
            "Models explore the objective and build shared understanding during this phase. "
            "Syntax: An integer. "
            "Default: 6. "
            "Example: discussion_turns=8"
        ),
    )

    synthesis_model: str = Route.adapter(  # type: ignore[assignment]
        default="chat_with_gemini3_pro_preview",
        description=(
            "(Optional) Large context model to use for synthesis phase. This model reviews the "
            "entire discussion and creates the final deliverable. Should have large context window. "
            "Available large context models: chat_with_gemini3_pro_preview (2M), chat_with_gpt41 (1M), "
            "chat_with_claude4_sonnet (1M). "
            "Syntax: A model tool name. "
            "Default: 'chat_with_gemini3_pro_preview'. "
            "Example: synthesis_model='chat_with_gpt41'"
        ),
    )

    validation_rounds: int = Route.adapter(  # type: ignore[assignment]
        default=2,
        description=(
            "(Optional) Number of validation rounds where original models review the synthesized deliverable. "
            "Models provide feedback and the synthesis agent refines based on input. "
            "Syntax: An integer. "
            "Default: 2. "
            "Example: validation_rounds=3"
        ),
    )
