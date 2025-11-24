"""Local service that returns a usage guide for The Force by reading a markdown file."""

from pathlib import Path
from typing import Dict, Optional


class InstructionsService:
    def __init__(self, default_path: str = "docs/INSTRUCTIONS.md") -> None:
        self.default_path = default_path

    async def execute(
        self, guide_path: Optional[str] = None, include_async: bool = False
    ) -> Dict[str, str]:
        """
        Return the contents of the instructions markdown file.

        Args:
            guide_path: Optional path to a markdown guide. If relative, resolved from CWD.
            include_async: Ignored for now; async guidance is part of the doc.
        """
        path = Path(guide_path or self.default_path)
        if not path.is_absolute():
            path = Path.cwd() / path

        if not path.exists():
            return {
                "error": f"Guide file not found: {path}. Provide guide_path or add docs/INSTRUCTIONS.md."
            }
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover
            return {"error": f"Failed to read guide: {exc}"}

        return {"instructions": content}
