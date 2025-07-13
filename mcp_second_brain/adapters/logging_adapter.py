"""Adapter for logging tools."""

import os
import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Any

from .base import BaseAdapter
from ..config import get_settings


class LoggingAdapter(BaseAdapter):
    """Adapter for logging-related tools."""

    model_name = "utility"
    context_window = 0
    description_snippet = "Logging utility adapter"

    def __init__(self, model_name: str = "utility"):
        self.model_name = model_name

    async def generate(
        self,
        prompt: str,
        vector_store_ids: List[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Handle logging tool execution."""

        # This adapter is specifically for the search_mcp_debug_logs tool
        # Extract the parameters that were routed here
        query = kwargs.get("query", "")
        level = kwargs.get("level")
        since = kwargs.get("since", "1h")
        instance_id = kwargs.get("instance_id")
        all_projects = kwargs.get("all_projects", False)
        limit = kwargs.get("limit", 100)

        return await self._search_logs(
            query=query,
            level=level,
            since=since,
            instance_id=instance_id,
            all_projects=all_projects,
            limit=limit,
        )

    async def _search_logs(
        self,
        query: str,
        level: str | None = None,
        since: str = "1h",
        instance_id: str | None = None,
        all_projects: bool = False,
        limit: int = 100,
    ) -> str:
        """Search through MCP debug logs."""
        settings = get_settings()

        if not settings.logging.developer_mode.enabled:
            return "Developer logging mode is not enabled. Set logging.developer_mode.enabled=true in config.yaml"

        db_path = settings.logging.developer_mode.db_path

        if not os.path.exists(db_path):
            return f"No log database found at {db_path}. Ensure the MCP server is running with developer logging enabled."

        # Input validation
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if level and level.upper() not in valid_levels:
            return f"Invalid log level '{level}'. Must be one of: {', '.join(valid_levels)}"

        # Validate limit - ensure it's an integer
        try:
            limit = int(limit) if isinstance(limit, str) else limit
        except (ValueError, TypeError):
            limit = 100  # Use safe default for invalid input

        if limit <= 0 or limit > 10000:  # Prevent excessive queries
            limit = 100  # Use safe default

        # Validate query string (prevent wildcard-only queries unless filtered)
        if query and query.strip() in ["%", "*", ""]:
            if not level and not instance_id:  # Only allow if other filters are present
                return "Wildcard-only queries require additional filters (level or instance_id)"

        # Build SQL query
        conditions = ["timestamp > ?"]
        params: list[str | float] = [self._parse_since(since)]

        # Filter by current project unless all_projects=True
        if not all_projects:
            conditions.append("project_cwd = ?")
            # Use current working directory since MCP_PROJECT_PATH isn't reliably set
            params.append(os.getcwd())

        if query:
            conditions.append("message LIKE ?")
            params.append(f"%{query}%")

        if level:
            conditions.append("level = ?")
            params.append(level.upper())

        if instance_id and instance_id.lower() != "any":
            conditions.append("instance_id = ?")
            params.append(instance_id)

        where_clause = " AND ".join(conditions)

        # Query database
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            cursor = conn.execute(
                f"""SELECT * FROM logs 
                    WHERE {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ?""",
                params + [limit],
            )

            results = []
            for row in cursor:
                log_entry = dict(row)
                if log_entry.get("extra"):
                    try:
                        log_entry["extra"] = json.loads(log_entry["extra"])
                    except Exception:
                        pass
                results.append(log_entry)

            conn.close()

            # Format results
            if not results:
                return "No logs found matching criteria"

            output = []
            output.append(f"Found {len(results)} log entries:\n")

            for log in results:
                timestamp = datetime.fromtimestamp(log["timestamp"]).isoformat()
                # Show project path if searching across all projects
                project_info = f" [{log['project_cwd']}]" if all_projects else ""
                output.append(
                    f"[{timestamp}] {log['level']} ({log['instance_id']}){project_info} "
                    f"{log['module']}: {log['message']}"
                )

                # Add extra info if it has useful content
                if log.get("extra") and isinstance(log["extra"], dict):
                    pathname = log["extra"].get("pathname")
                    lineno = log["extra"].get("lineno")
                    if pathname and lineno:
                        output.append(f"  at {pathname}:{lineno}")

            return "\n".join(output)

        except Exception as e:
            return f"Error searching logs: {e}"

    def _parse_since(self, since_str: str) -> float:
        """Parse time duration string to timestamp with validation."""
        now = datetime.now()

        try:
            # Parse duration with validation
            if since_str.endswith("m"):
                minutes = int(since_str[:-1])
                if minutes < 0 or minutes > 525600:  # Max 1 year in minutes
                    raise ValueError("Minutes out of valid range")
                delta = timedelta(minutes=minutes)
            elif since_str.endswith("h"):
                hours = int(since_str[:-1])
                if hours < 0 or hours > 8760:  # Max 1 year in hours
                    raise ValueError("Hours out of valid range")
                delta = timedelta(hours=hours)
            elif since_str.endswith("d"):
                days = int(since_str[:-1])
                if days < 0 or days > 365:  # Max 1 year in days
                    raise ValueError("Days out of valid range")
                delta = timedelta(days=days)
            else:
                delta = timedelta(hours=1)  # Default 1 hour

            result_timestamp = (now - delta).timestamp()

            # Validate result is reasonable (not negative, not too far in past)
            if result_timestamp < 0:
                raise ValueError("Resulting timestamp is negative")

            return result_timestamp

        except (ValueError, OverflowError):
            # Return a reasonable default (1 hour ago) for invalid input
            return (now - timedelta(hours=1)).timestamp()
