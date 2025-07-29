"""Local service for describing/summarizing sessions."""

import json
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
            tool=model_to_use,  # FIX: Use the summarization model's name, not the original tool
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
            # The executor will fetch the history from temp_session_id automatically

            # Check if model is a Gemini model
            if not model_to_use.startswith(("chat_with_gemini", "gemini")):
                return f"Error: Only Gemini models are supported for summarization. Got '{model_to_use}'"

            # Build the structured instructions with XML format
            extra_instructions = kwargs.get("extra_instructions", "")
            instructions = f"""<task>
Generate a structured JSON summary of this conversation following the schema and rules below.
</task>

<analysis_steps>
1. First, analyze the conversation to determine its complexity:
   - Count the total messages
   - Estimate the duration (based on timestamps if available)
   - Assess the depth and complexity of topics discussed
   
2. Based on this analysis, assign a session_type:
   - "minimal": 2-10 messages, simple Q&A, < 10 minutes
   - "standard": 10-30 messages, moderate complexity, 10-30 minutes  
   - "detailed": 30+ messages, complex implementation/debugging, 30+ minutes
</analysis_steps>

<schema>
{{
  "type": "object",
  "properties": {{
    "one_liner": {{
      "type": "string",
      "maxLength": 120,
      "description": "Single-line summary of the session's outcome or purpose"
    }},
    "summary": {{
      "type": "string", 
      "description": "1-3 paragraph narrative overview"
    }},
    "session_type": {{
      "type": "string",
      "enum": ["minimal", "standard", "detailed"]
    }},
    "custom": {{
      "type": "string",
      "description": "Response to extra_instructions if provided, empty string otherwise"
    }},
    "timeline": {{
      "type": "array",
      "description": "Only include for detailed sessions",
      "items": {{
        "type": "object",
        "properties": {{
          "phase": {{"type": "string"}},
          "summary": {{"type": "string"}},
          "key_moments": {{"type": "array", "items": {{"type": "string"}}}}
        }}
      }}
    }},
    "outcomes": {{
      "type": "object",
      "description": "Only include for standard/detailed sessions if non-empty",
      "properties": {{
        "decisions": {{"type": "array", "items": {{"type": "string"}}}},
        "insights": {{"type": "array", "items": {{"type": "string"}}}},
        "challenges": {{"type": "array", "items": {{"type": "string"}}}},
        "next_steps": {{"type": "array", "items": {{"type": "string"}}}}
      }}
    }},
    "artifacts": {{
      "type": "object",
      "description": "Only include for standard/detailed sessions if non-empty",
      "properties": {{
        "files": {{"type": "array", "items": {{"type": "string"}}}},
        "errors": {{"type": "array", "items": {{"type": "string"}}}},
        "tools": {{"type": "array", "items": {{"type": "string"}}}}
      }}
    }},
    "metrics": {{
      "type": "object",
      "description": "Include for standard/detailed sessions",
      "properties": {{
        "message_count": {{"type": "integer"}},
        "duration_seconds": {{"type": "integer"}}
      }}
    }}
  }}
}}
</schema>

<rules>
1. ALWAYS include the four core fields: one_liner, summary, session_type, custom
2. For "minimal" sessions: Include ONLY the required fields
3. For "standard" sessions: Add outcomes/artifacts/metrics ONLY if they have content
4. For "detailed" sessions: Include timeline and all relevant optional fields
5. NEVER include empty arrays or empty objects - omit the field entirely instead
6. The one_liner must be ≤ 120 characters
7. The summary should be 1-3 paragraphs providing narrative context
{f'''8. For the custom field: {extra_instructions}''' if extra_instructions else '8. The custom field should be an empty string since no extra_instructions were provided'}
</rules>

<examples>
<example_minimal>
{{
  "one_liner": "Located JWT validation in auth/validators.py",
  "summary": "User asked about the location of JWT validation logic. The assistant found and identified the `validate_jwt_token()` function in `auth/validators.py` at line 45.",
  "session_type": "minimal",
  "custom": ""
}}
</example_minimal>

<example_detailed>
{{
  "one_liner": "Implemented session management tools with TDD approach",
  "summary": "A comprehensive implementation session adding list_sessions and describe_session tools to the MCP server. The development followed test-driven development practices, starting with failing tests and implementing functionality incrementally. Major challenges included resolving circular import issues and discovering that sessions were being truncated due to a 1-hour TTL setting. The session concluded with successful implementation of both tools, including structured JSON output for summaries and a caching mechanism.",
  "session_type": "detailed",
  "custom": "",
  "timeline": [
    {{
      "phase": "Initial Planning and Setup",
      "summary": "Discussed requirements for session management tools and began TDD implementation",
      "key_moments": [
        "Defined list_sessions tool requirements with search and filtering",
        "Created pytest fixtures for database isolation",
        "Wrote initial failing tests"
      ]
    }},
    {{
      "phase": "Implementation and Debugging",
      "summary": "Built both tools while resolving technical challenges",
      "key_moments": [
        "Implemented list_sessions with LocalService pattern",
        "Discovered and fixed circular import issues",
        "Created describe_session using session duplication approach"
      ]
    }},
    {{
      "phase": "TTL Investigation",
      "summary": "Discovered sessions were being deleted after 1 hour",
      "key_moments": [
        "Found 60-message session reduced to 3 messages",
        "Identified TTL cleanup as root cause",
        "Updated default TTL from 1 hour to 6 months"
      ]
    }}
  ],
  "outcomes": {{
    "decisions": [
      "Use separate SQLite table for summary caching",
      "Implement session duplication approach for describe_session",
      "Increase default TTL to 6 months"
    ],
    "insights": [
      "Sessions were being truncated due to aggressive TTL cleanup",
      "Circular imports can be resolved via deferred imports"
    ],
    "challenges": [
      "Initial 'missing context parameter' error in describe_session",
      "Session cache key mismatch between creation and lookup"
    ],
    "next_steps": [
      "Implement structured JSON schema for summaries",
      "Update list_sessions to handle JSON summaries"
    ]
  }},
  "artifacts": {{
    "files": [
      "mcp_the_force/local_services/list_sessions.py",
      "mcp_the_force/local_services/describe_session.py",
      "mcp_the_force/unified_session_cache.py",
      "config.yaml"
    ],
    "errors": [
      "ambiguous column name: session_id",
      "Missing required parameter: context"
    ],
    "tools": [
      "todo_write",
      "edit",
      "bash",
      "grep",
      "mcp__the-force__chat_with_gemini25_pro"
    ]
  }},
  "metrics": {{
    "message_count": 84,
    "duration_seconds": 7200
  }}
}}
</example_detailed>
</examples>"""

            # Define the structured output schema (Gemini-friendly without strict enforcement)
            structured_output_schema = {
                "type": "object",
                "properties": {
                    "one_liner": {
                        "type": "string",
                        "maxLength": 120,
                        "description": "Single-line summary of the session's outcome or purpose",
                    },
                    "summary": {
                        "type": "string",
                        "description": "1-3 paragraph narrative overview",
                    },
                    "session_type": {
                        "type": "string",
                        "enum": ["minimal", "standard", "detailed"],
                    },
                    "custom": {
                        "type": "string",
                        "description": "Response to extra_instructions if provided, empty string otherwise",
                    },
                    "timeline": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "phase": {"type": "string"},
                                "summary": {"type": "string"},
                                "key_moments": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "outcomes": {
                        "type": "object",
                        "properties": {
                            "decisions": {"type": "array", "items": {"type": "string"}},
                            "insights": {"type": "array", "items": {"type": "string"}},
                            "challenges": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "next_steps": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                    "artifacts": {
                        "type": "object",
                        "properties": {
                            "files": {"type": "array", "items": {"type": "string"}},
                            "errors": {"type": "array", "items": {"type": "string"}},
                            "tools": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "metrics": {
                        "type": "object",
                        "properties": {
                            "message_count": {"type": "integer", "minimum": 0},
                            "duration_seconds": {"type": "integer", "minimum": 0},
                        },
                    },
                },
            }

            params = {
                "session_id": temp_session_id,
                "instructions": instructions,
                "output_format": "Valid JSON object following the provided schema",
                "structured_output_schema": structured_output_schema,
                "context": [],  # Empty context - all data is in the session history
            }

            # Execute the summarization
            # Import here to avoid circular dependency
            from ..tools.executor import executor

            summary_response = await executor.execute(metadata, **params)

            # Validate that we got valid JSON
            try:
                summary_json = json.loads(summary_response)
                # Re-serialize to ensure consistent formatting
                summary = json.dumps(summary_json)
            except json.JSONDecodeError:
                # Fallback if the model didn't return valid JSON
                summary = json.dumps(
                    {
                        "one_liner": "Failed to generate structured summary",
                        "summary": summary_response[
                            :500
                        ],  # First 500 chars of response
                        "session_type": "minimal",
                        "custom": "",
                    }
                )

            # 5. Cache the summary under the original session ID
            await UnifiedSessionCache.set_summary(project, tool, session_id, summary)

            return summary

        finally:
            # Clean up the temporary session using the correct tool name
            await UnifiedSessionCache.delete_session(
                project, model_to_use, temp_session_id
            )
