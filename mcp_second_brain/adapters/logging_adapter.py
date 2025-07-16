"""Adapter for logging tools using VictoriaLogs."""

import json
import os
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
        # Extract new parameter names
        text = kwargs.get("text")
        severity = kwargs.get("severity")
        since = kwargs.get("since", "1h")
        until = kwargs.get("until", "now")
        project = kwargs.get("project", "current")
        context = kwargs.get("context", "*")
        instance = kwargs.get("instance", "*")
        limit = kwargs.get("limit", 100)
        order = kwargs.get("order", "desc")

        return await self._search_logs(
            text=text,
            severity=severity,
            since=since,
            until=until,
            project=project,
            context=context,
            instance=instance,
            limit=limit,
            order=order,
        )

    async def _search_logs(
        self,
        text: str | None = None,
        severity: str | List[str] | None = None,
        since: str = "1h",
        until: str = "now",
        project: str = "current",
        context: str = "*",
        instance: str = "*",
        limit: int = 100,
        order: str = "desc",
    ) -> str:
        """Search logs using VictoriaLogs LogsQL with improved LLM-friendly interface."""
        settings = get_settings()

        if not settings.logging.developer_mode.enabled:
            return "Developer logging mode is not enabled. Set logging.developer_mode.enabled=true in config.yaml"

        try:
            # Build LogsQL query with VictoriaLogs label syntax
            filters = ["app:mcp-second-brain"]  # Always filter to our app

            # Handle severity filter (single value or list)
            if severity:
                if isinstance(severity, list):
                    # Multiple severities: severity:(info OR warning OR error)
                    severity_filter = (
                        "severity:(" + " OR ".join(s.lower() for s in severity) + ")"
                    )
                    filters.append(severity_filter)
                else:
                    filters.append(f"severity:{severity.lower()}")

            # Handle project filter
            if project == "current":
                # Default: filter to current project
                current_project = os.getenv("MCP_PROJECT_PATH", os.getcwd())
                filters.append(f'project:"{current_project}"')
            elif project != "all":
                # Specific project path
                filters.append(f'project:"{project}"')
            # else: project == "all" means no project filter

            # Handle context filter (dev/test/e2e from instance_id)
            if context != "*":
                # Match the middle part of semantic instance IDs
                filters.append(f'instance_id~".*_{context}_.*"')

            # Handle instance filter
            if instance != "*":
                if "*" in instance:
                    # Wildcard pattern
                    regex_pattern = instance.replace("*", ".*")
                    filters.append(f'instance_id~"{regex_pattern}"')
                else:
                    # Exact match
                    filters.append(f'instance_id:"{instance}"')

            # Build base query
            logsql = " ".join(filters)

            # Add text search
            if text:
                logsql += f' "{text}"'

            # Add time filter
            if until == "now":
                logsql = f"{logsql} _time:{since}"
            else:
                # Both since and until specified
                logsql = f"{logsql} _time:[{since}, {until}]"

            # Add sorting and limit
            if order == "asc":
                logsql += " | sort by (_time)"
            logsql += f" | limit {limit}"

            # Query VictoriaLogs (VictoriaLogs returns ND-JSON but we can get it all at once)
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/select/logsql/query",
                    data={"query": logsql},
                    timeout=30.0,
                )
                response.raise_for_status()

                results = []
                # Parse ND-JSON response (one JSON object per line)
                for line in response.text.strip().split("\n"):
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
                if severity:
                    suggestions.append(
                        f"Try removing severity filter (currently: {severity})"
                    )
                if instance != "*":
                    suggestions.append("Try broader instance filter or remove it")
                if project == "current":
                    suggestions.append('Try searching all projects with project="all"')

                suggestion_text = (
                    f" Suggestions: {'; '.join(suggestions)}" if suggestions else ""
                )
                return f"No logs found matching criteria.{suggestion_text}"

            # LLM-optimized formatting
            time_desc = f"last {since}" if until == "now" else f"{since} to {until}"
            output = [f"## Found {len(results)} log entries ({time_desc})"]

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
