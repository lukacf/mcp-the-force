"""Local service that returns a usage guide for The Force by reading a markdown file."""

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
        path = Path(candidate)
        if not path.is_absolute():
            # prefer repo-local docs if present
            repo_path = Path.cwd() / path
            if repo_path.exists():
                path = repo_path
            else:
                # fall back to installed package location
                pkg_root = Path(__file__).resolve().parent.parent  # mcp_the_force/
                fallback = pkg_root.parent / "docs" / "INSTRUCTIONS.md"
                path = fallback if fallback.exists() else repo_path

        if not path.exists():
            return {
                "error": f"Guide file not found: {path}. Provide guide_path or ensure docs/INSTRUCTIONS.md is available."
            }
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover
            return {"error": f"Failed to read guide: {exc}"}

        return {"instructions": content}
