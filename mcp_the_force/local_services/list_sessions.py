"""Local service for listing sessions."""

import json
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
            search: Optional substring search on session_id
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
        # Note: Sessions are now keyed by (project, session_id), tool info is per-turn in history
        if include_summary:
            query = """
                SELECT s.session_id, ss.summary
                FROM unified_sessions s
                LEFT JOIN session_summaries ss
                    ON s.project = ss.project AND s.session_id = ss.session_id
                WHERE s.project = ?
            """
        else:
            query = """
                SELECT session_id
                FROM unified_sessions
                WHERE project = ?
            """

        # Add search filter if provided (searches session_id only)
        if search:
            if include_summary:
                query += " AND s.session_id LIKE ?"
            else:
                query += " AND session_id LIKE ?"
            like_pattern = f"%{search}%"
            params.append(like_pattern)

        # Add ordering and limit
        if include_summary:
            query += " ORDER BY s.updated_at DESC LIMIT ?"
        else:
            query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        # Execute query using the async-safe method
        rows = await cache._execute_async(query, tuple(params))

        # Convert to list of dicts
        results = []
        if rows:
            for row in rows:
                session_data = {"session_id": row[0]}
                if include_summary:
                    # The summary is the second column (index 1), may be None
                    summary_raw = row[1]
                    if summary_raw:
                        try:
                            # Try to parse as JSON and extract one_liner
                            summary_json = json.loads(summary_raw)
                            session_data["summary"] = summary_json.get(
                                "one_liner", summary_raw
                            )
                        except (json.JSONDecodeError, AttributeError):
                            # Fallback to raw summary if not valid JSON
                            session_data["summary"] = summary_raw
                    else:
                        session_data["summary"] = None
                results.append(session_data)

        return results
