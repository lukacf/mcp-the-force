"""Local service that forwards raw LogsQL to VictoriaLogs and prettifies the reply."""

import json
import httpx
import textwrap
from typing import Any

from ..config import get_settings

MAX_LINES_RETURNED = 120  # hard cap to keep LLM context small
TRUNCATE_MSG_AT = 200  # characters


class LoggingService:
    """Local service for executing raw LogsQL queries."""

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.logging.victoria_logs_url

    async def execute(self, **kwargs: Any) -> str:
        """Execute raw LogsQL query and return formatted results."""
        settings = get_settings()
        if not settings.logging.developer_mode.enabled:
            return (
                "Developer logging mode is disabled. "
                "Set logging.developer_mode.enabled=true in config.yaml"
            )

        query = (kwargs.get("query") or "").strip()
        if not query:
            return "Missing required parameter: `query` (raw LogsQL string)"

        return await self._execute_logsql(query)

    async def _execute_logsql(self, query: str) -> str:
        """Execute raw LogsQL query and format results."""
        try:
            # Call VictoriaLogs
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/select/logsql/query",
                    data={"query": query},
                    timeout=30.0,
                )
                resp.raise_for_status()
        except httpx.HTTPError as e:
            return f"Could not reach VictoriaLogs on {self.base_url}: {e}"

        # Parse ND-JSON (newline-delimited JSON)
        lines = [line for line in resp.text.splitlines() if line.strip()]
        if not lines:
            return "No results. Ensure your query includes a time filter like _time:5m"

        # Format results
        pretty = [
            f"## {len(lines):,} log lines returned (showing first {min(len(lines), MAX_LINES_RETURNED)})"
        ]

        for i, raw in enumerate(lines[:MAX_LINES_RETURNED], start=1):
            try:
                log = json.loads(raw)
            except json.JSONDecodeError:
                pretty.append(f"[{i:03}] <invalid JSON line>")
                continue

            # Extract key fields
            ts = log.get("_time", "")[:23]  # Truncate microseconds
            sev = log.get("severity", "").upper()[:5]  # Truncate to 5 chars
            msg = log.get("_msg", "") or log.get("message", "")

            # Truncate long messages
            if len(msg) > TRUNCATE_MSG_AT:
                msg = msg[:TRUNCATE_MSG_AT] + "…"

            # Format main line
            if sev:
                pretty.append(f"[{i:03}] {ts} [{sev}] {msg}")
            else:
                pretty.append(f"[{i:03}] {ts} {msg}")

            # Add labels/fields (excluding internal fields)
            labels = {
                k: v
                for k, v in log.items()
                if k not in {"_time", "_msg", "message", "severity"}
                and not k.startswith("_stream")
                and v  # Skip empty values
            }

            if labels:
                # Format labels nicely
                label_parts = []
                for k, v in sorted(labels.items()):
                    if isinstance(v, str) and len(v) > 50:
                        v = v[:50] + "…"
                    label_parts.append(f"{k}={v}")

                if label_parts:
                    wrapped = textwrap.fill(
                        ", ".join(label_parts),
                        width=80,
                        initial_indent="      ",
                        subsequent_indent="      ",
                    )
                    pretty.append(wrapped)

        if len(lines) > MAX_LINES_RETURNED:
            pretty.append(
                f"\n… {len(lines) - MAX_LINES_RETURNED:,} more lines truncated. "
                f"Use pipes like '| head 20' or '| stats' to control output."
            )

        return "\n".join(pretty)
