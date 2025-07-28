"""Local service for listing sessions."""

import os
from typing import List, Dict, Any, Optional
from ..config import get_settings
from ..unified_session_cache import _get_instance as get_cache_instance


class ListSessionsService:
    """Service for listing existing sessions."""

    async def execute(
        self,
        limit: int = 5,
        search: Optional[str] = None,
        include_summary: bool = False,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """List sessions from the database.

        Args:
            limit: Maximum number of sessions to return (default: 5)
            search: Optional substring search on session_id and tool_name
            include_summary: Whether to include summary in results (default: False)

        Returns:
            List of session information
        """
        # Get current project name
        settings = get_settings()
        project_path = settings.logging.project_path or os.getcwd()
        project_name = os.path.basename(project_path)

        # Get cache instance
        cache = get_cache_instance()

        # Build query dynamically
        params: List[Any] = [project_name]

        # Base query - with optional summary join
        if include_summary:
            query = """
                SELECT s.tool as tool_name, s.session_id, ss.summary
                FROM unified_sessions s
                LEFT JOIN session_summaries ss 
                    ON s.project = ss.project AND s.tool = ss.tool AND s.session_id = ss.session_id
                WHERE s.project = ?
            """
        else:
            query = """
                SELECT tool as tool_name, session_id
                FROM unified_sessions
                WHERE project = ?
            """

        # Add search filter if provided
        if search:
            query += " AND (session_id LIKE ? OR tool LIKE ?)"
            like_pattern = f"%{search}%"
            params.extend([like_pattern, like_pattern])

        # Add ordering and limit
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        # Execute query using the async-safe method
        rows = await cache._execute_async(query, tuple(params))

        # Convert to list of dicts
        results = []
        if rows:
            for row in rows:
                session_data = {"tool_name": row[0], "session_id": row[1]}
                if include_summary:
                    # The summary is the third column (index 2), may be None
                    session_data["summary"] = row[2]
                results.append(session_data)

        return results
