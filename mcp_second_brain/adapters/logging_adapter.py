"""Adapter for logging tools using VictoriaLogs."""

import os
import httpx
from typing import List, Any

from .base import BaseAdapter
from ..config import get_settings


class LoggingAdapter(BaseAdapter):
    """Adapter for VictoriaLogs-based logging tools."""

    model_name = "utility"
    context_window = 0
    description_snippet = "VictoriaLogs utility adapter"

    def __init__(self, model_name: str = "utility"):
        self.model_name = model_name
        self.base_url = "http://localhost:9428"

    async def generate(
        self,
        prompt: str,
        vector_store_ids: List[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Handle logging tool execution."""
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
        """Search logs using VictoriaLogs LogsQL."""
        settings = get_settings()

        if not settings.logging.developer_mode.enabled:
            return "Developer logging mode is not enabled. Set logging.developer_mode.enabled=true in config.yaml"

        try:
            # Build LogsQL query
            filters = []
            if level:
                filters.append(f'level:="{level.upper()}"')
            if instance_id:
                filters.append(f'instance_id:="{instance_id}"')
            if not all_projects:
                current_project = os.getenv("MCP_PROJECT_PATH", os.getcwd())
                filters.append(f'project:="{current_project}"')

            # Combine filters
            logsql = " AND ".join(filters) if filters else ""

            # Add text search
            if query:
                if logsql:
                    logsql += f' AND "{query}"'
                else:
                    logsql = f'"{query}"'

            # Add time filter and limit
            logsql = f"({logsql}) AND _time:{since}" if logsql else f"_time:{since}"
            logsql += f" | limit {limit}"

            # Query VictoriaLogs
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/select/logsql/query",
                    data={"query": logsql},
                    timeout=30.0,
                )
                response.raise_for_status()

            results = response.json()

            if not results:
                return "No logs found matching criteria"

            # Format results
            output = [f"Found {len(results)} log entries:\n"]

            for log in results:
                timestamp = log.get("_time", "unknown")
                level_val = log.get("level", "INFO")
                message = log.get("_msg", log.get("message", ""))
                project_info = f" [{log.get('project', '')}]" if all_projects else ""

                output.append(f"[{timestamp}] {level_val}{project_info}: {message}")

            return "\n".join(output)

        except httpx.HTTPError as e:
            return f"Cannot connect to VictoriaLogs on {self.base_url}. Ensure container is running. Error: {e}"
        except Exception as e:
            return f"Error searching logs: {e}"
