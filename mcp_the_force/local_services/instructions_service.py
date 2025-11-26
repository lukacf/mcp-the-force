"""Local service that returns a usage guide for The Force by reading a markdown file."""

import importlib.resources as pkg_resources
from pathlib import Path
from typing import Any, Dict, Optional


class InstructionsService:
    def __init__(self, default_path: str = "docs/INSTRUCTIONS.md") -> None:
        # Use repository-local default if it exists; otherwise fall back to packaged docs
        self.default_path = default_path

    async def execute(
        self,
        guide_path: Optional[str] = None,
        include_async: bool | str = False,
        **_: Any,
    ) -> Dict[str, str]:
        """
        Return the contents of the instructions markdown file.

        Args:
            guide_path: Optional path to a markdown guide. If relative, resolved from CWD.
            include_async: When truthy, append an async usage tip.
        """
        # Coerce include_async from string/bool
        if isinstance(include_async, str):
            include_async = include_async.lower() in {"1", "true", "yes", "y"}

        candidate = guide_path or self.default_path
        paths_to_try = []

        p = Path(candidate)
        if p.is_absolute():
            paths_to_try.append(p)
        else:
            paths_to_try.append(Path.cwd() / p)  # caller's CWD
            # repo-root fallback (two levels up from this file)
            paths_to_try.append(
                Path(__file__).resolve().parents[2] / "docs" / "INSTRUCTIONS.md"
            )
            # package data (if bundled)
            try:
                pkg_docs = (
                    pkg_resources.files("mcp_the_force") / "docs" / "INSTRUCTIONS.md"
                )
                paths_to_try.append(Path(str(pkg_docs)))
            except Exception:
                pass

        for path in paths_to_try:
            if path.exists():
                try:
                    return {"instructions": path.read_text(encoding="utf-8")}
                except Exception as exc:  # pragma: no cover
                    return {"error": f"Failed to read guide: {exc}"}

        # Ultimate fallback: short inline guide
        fallback = (
            "The Force MCP Guide unavailable on disk. Core usage: "
            "use chat_with_* tools with absolute paths in context/priority_context; "
            "set session_id to persist history; use start_job/poll_job/cancel_job for long tasks; "
            "group_think orchestrates multiple models; see docs/INSTRUCTIONS.md for full details."
        )
        return {"instructions": fallback}
