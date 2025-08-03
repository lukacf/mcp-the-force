"""Data models for token budget optimization."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class FileInfo:
    """Information about a file for optimization decisions."""

    path: str
    content: str  # File content (empty for overflow files)
    size: int
    tokens: int  # Exact token count
    mtime: int  # Modification time for change detection


@dataclass
class Plan:
    """Final plan for context distribution."""

    inline_files: List[FileInfo]
    overflow_files: List[FileInfo]
    file_tree: str
    total_prompt_tokens: int
    iterations: int
    optimized_prompt: str  # The final optimized XML prompt
    messages: List[dict]  # Complete message list (dev + history + user)
    overflow_paths: Optional[List[str]] = None  # For backward compatibility

    @property
    def inline_paths(self) -> List[str]:
        """Get list of inline file paths."""
        return [f.path for f in self.inline_files]

    def get_overflow_paths(self) -> List[str]:
        """Get list of overflow file paths."""
        if self.overflow_paths is not None:
            return self.overflow_paths
        return [f.path for f in self.overflow_files]


@dataclass
class BudgetSnapshot:
    """Snapshot of token budget state during optimization."""

    model_limit: int
    fixed_reserve: int
    history_tokens: int
    overhead_tokens: int
    available_budget: int
    prompt_tokens: int

    @property
    def overage(self) -> int:
        """How many tokens we exceed the limit by (0 if under)."""
        return max(0, self.prompt_tokens - self.model_limit)

    @property
    def fits(self) -> bool:
        """Whether the current prompt fits within model limits."""
        return self.prompt_tokens <= self.model_limit
