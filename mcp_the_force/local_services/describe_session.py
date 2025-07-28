"""Local service for describing/summarizing sessions."""

import uuid
from typing import Optional, Tuple
from ..unified_session_cache import (
    _get_instance as get_cache_instance,
    UnifiedSessionCache,
    UnifiedSession,
)
from ..config import get_settings


class DescribeSessionService:
    """Service for generating AI-powered summaries of sessions."""

    async def _find_session_context(self, session_id: str) -> Optional[Tuple[str, str]]:
        """Find the project and tool for a session by its ID.

        Returns:
            Tuple of (project, tool) if found, None otherwise
        """
        cache = get_cache_instance()

        # Query to find the session by ID only
        rows = await cache._execute_async(
            "SELECT project, tool FROM unified_sessions WHERE session_id = ? LIMIT 1",
            (session_id,),
        )

        if rows:
            return (rows[0][0], rows[0][1])
        return None

    async def execute(self, session_id: str, **kwargs) -> str:
        """Generate a summary of a session using AI.

        Args:
            session_id: The session ID to summarize
            summarization_model: Optional model to use for summarization
            extra_instructions: Optional additional instructions for the summary

        Returns:
            Summary text or error message
        """
        # Prevent recursive summarization
        settings = get_settings()
        model_to_use = (
            kwargs.get("summarization_model")
            or settings.tools.default_summarization_model
        )
        if model_to_use == "describe_session":
            return "Error: Recursive summarization is not allowed."

        # First, find the session context
        session_context = await self._find_session_context(session_id)
        if not session_context:
            return f"Error: Session '{session_id}' not found."

        project, tool = session_context

        # Check if we have a cached summary
        cached_summary = await UnifiedSessionCache.get_summary(
            project, tool, session_id
        )
        if cached_summary:
            return cached_summary

        # Cache miss - need to generate summary
        # 1. Get the original session
        original_session = await UnifiedSessionCache.get_session(
            project, tool, session_id
        )
        if not original_session:
            return f"Error: Session '{session_id}' not found in cache."

        # 2. Create a duplicate session with temp ID
        temp_session_id = f"temp-summary-{session_id}-{uuid.uuid4().hex[:8]}"
        temp_session = UnifiedSession(
            project=original_session.project,
            tool=original_session.tool,
            session_id=temp_session_id,
            updated_at=original_session.updated_at,
            history=original_session.history.copy(),
            provider_metadata=original_session.provider_metadata.copy(),
        )

        # 3. Save the temporary session
        await UnifiedSessionCache.set_session(temp_session)

        # 4. Execute summarization using the duplicated session
        try:
            # Get the tool metadata for the summarization model
            # Import here to avoid circular dependency
            from ..tools.registry import get_tool

            metadata = get_tool(model_to_use)
            if not metadata:
                return f"Error: Summarization model '{model_to_use}' not found."

            # Build params for executor
            params = {
                "session_id": temp_session_id,
                "instructions": "Summarize this conversation."
                + (
                    f" {kwargs.get('extra_instructions', '')}"
                    if kwargs.get("extra_instructions")
                    else ""
                ),
                "output_format": "A concise summary of the conversation",
            }

            # Execute the summarization
            # Import here to avoid circular dependency
            from ..tools.executor import executor

            summary = await executor.execute(metadata, **params)

            # 5. Cache the summary under the original session ID
            await UnifiedSessionCache.set_summary(project, tool, session_id, summary)

            return summary

        finally:
            # Clean up the temporary session
            await UnifiedSessionCache.delete_session(project, tool, temp_session_id)
