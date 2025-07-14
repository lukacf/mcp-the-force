"""Adapter for logging tools using VictoriaLogs."""

import os
import json
import httpx
from typing import List, Any, Dict

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
        """Search logs using VictoriaLogs LogsQL with improved LLM-friendly interface."""
        settings = get_settings()

        if not settings.logging.developer_mode.enabled:
            return "Developer logging mode is not enabled. Set logging.developer_mode.enabled=true in config.yaml"

        try:
            # Smart defaults and inference
            # Auto-infer severity from query text
            if not level and query:
                if any(
                    word in query.lower() for word in ["failed", "error", "exception"]
                ):
                    level = "ERROR"
                elif any(word in query.lower() for word in ["warning", "warn"]):
                    level = "WARNING"

            # Auto-infer time range from query text
            if "recently" in query.lower() or "just now" in query.lower():
                since = "10m"
            elif "last hour" in query.lower():
                since = "1h"

            # Build LogsQL query with VictoriaLogs label syntax
            filters = ["app:mcp-second-brain"]  # Always filter to our app

            if level:
                filters.append(f'severity:"{level.upper()}"')
            if instance_id:
                # Support wildcards for semantic instance IDs
                if "*" in instance_id:
                    filters.append(f'instance_id~"{instance_id}"')
                else:
                    filters.append(f'instance_id:"{instance_id}"')
            if not all_projects:
                current_project = os.getenv("MCP_PROJECT_PATH", os.getcwd())
                filters.append(f'project:"{current_project}"')

            # Build base query
            logsql = " AND ".join(filters)

            # Add text search
            if query:
                logsql += f' AND "{query}"'

            # Add time filter and limit
            logsql = f"({logsql}) AND _time:{since}"
            logsql += f" | sort _time desc | limit {limit}"

            # Query VictoriaLogs with streaming ND-JSON parsing
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/select/logsql/query",
                    data={"query": logsql},
                    timeout=30.0,
                ) as response:
                    response.raise_for_status()

                    results = []
                    async for line in response.aiter_lines():
                        if line.strip():  # Skip empty lines
                            try:
                                log_entry = json.loads(line)
                                results.append(log_entry)
                            except json.JSONDecodeError as e:
                                return f"JSON parse error on line: {e}"

            if not results:
                suggestions = []
                if since == "1h":
                    suggestions.append("Try broadening time range to '2h' or '1d'")
                if level:
                    suggestions.append(
                        f"Try removing level filter (currently: {level})"
                    )
                if instance_id and "*" not in instance_id:
                    suggestions.append(
                        "Try using wildcard like 'mcp-second-brain_dev_*'"
                    )

                suggestion_text = (
                    f" Suggestions: {'; '.join(suggestions)}" if suggestions else ""
                )
                return f"No logs found matching criteria.{suggestion_text}"

            # LLM-optimized formatting
            output = [f"## Found {len(results)} log entries (last {since})"]

            # Group by instance for better readability
            by_instance: Dict[str, List[Dict[str, Any]]] = {}
            for log in results:
                inst_id = log.get("instance_id", "unknown")
                if inst_id not in by_instance:
                    by_instance[inst_id] = []
                by_instance[inst_id].append(log)

            for inst_id, logs in by_instance.items():
                output.append(f"\n### Instance: {inst_id} ({len(logs)} entries)")

                for log in logs[-10:]:  # Show last 10 per instance
                    timestamp = log.get("_time", "unknown")[:19]  # Truncate timestamp
                    severity = log.get("severity", "INFO")
                    message = log.get("_msg", "")

                    # Truncate very long messages
                    if len(message) > 200:
                        message = message[:200] + "..."

                    output.append(f"[{timestamp}] {severity}: {message}")

            return "\n".join(output)

        except httpx.HTTPError as e:
            return f"Cannot connect to VictoriaLogs on {self.base_url}. Ensure container is running. Error: {e}"
        except json.JSONDecodeError as e:
            return f"Error parsing VictoriaLogs response: {e}"
        except Exception as e:
            return f"Error searching logs: {e}"
