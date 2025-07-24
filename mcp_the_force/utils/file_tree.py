"""Build file tree visualization for context/attachment clarity."""

import os
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


def build_file_tree_from_paths(
    all_paths: List[str],
    attachment_paths: List[str],
    root_path: Optional[Path] = None,
) -> str:
    """Build a file tree from a list of paths, marking attachment files.

    This is an alternative implementation that builds the tree from
    a pre-gathered list of paths rather than walking the filesystem.

    Args:
        all_paths: All file paths to include in the tree
        attachment_paths: Paths that should be marked as attached
        root_path: Optional root path for display (defaults to common root)

    Returns:
        ASCII tree representation with attached markers
    """
    if not all_paths:
        return "(empty)"

    # Normalize all paths and convert to Path objects
    all_paths_normalized = [Path(os.path.normpath(p)) for p in all_paths]
    attachment_set = {os.path.normpath(p) for p in attachment_paths}

    # Group paths by their common ancestors
    # This handles files from different drives/mount points better
    path_groups: Dict[Path, List[Path]] = {}

    for path in all_paths_normalized:
        # Find the best grouping for this path
        added = False
        for root in list(path_groups.keys()):
            try:
                # Check if this path is under an existing root
                path.relative_to(root)
                path_groups[root].append(path)
                added = True
                break
            except ValueError:
                # Check if the existing root is under this path's parent
                try:
                    root.relative_to(path.parent)
                    # Move all paths from old root to new root
                    if path.parent not in path_groups:
                        path_groups[path.parent] = []
                    path_groups[path.parent].extend(path_groups[root])
                    path_groups[path.parent].append(path)
                    del path_groups[root]
                    added = True
                    break
                except ValueError:
                    continue

        if not added:
            # This path doesn't fit under any existing root
            # Find the most sensible root for it
            if len(all_paths_normalized) == 1:
                # Single file - use its parent
                path_groups[path.parent] = [path]
            else:
                # Multiple files - try to find a common ancestor with other paths
                best_root = path.parent
                for other_path in all_paths_normalized:
                    if other_path != path:
                        try:
                            common = Path(
                                os.path.commonpath([str(path), str(other_path)])
                            )
                            if len(common.parts) > len(best_root.parts):
                                best_root = common
                        except ValueError:
                            # No common path
                            pass

                if best_root not in path_groups:
                    path_groups[best_root] = []
                path_groups[best_root].append(path)

    # Build tree structure for each group
    lines: List[str] = []

    for root, paths in sorted(path_groups.items()):
        if lines:  # Add spacing between groups
            lines.append("")

        # Build tree for this group
        tree: Dict[str, Any] = {}

        for path in paths:
            try:
                rel_path = path.relative_to(root)
                parts = rel_path.parts
            except ValueError:
                # Shouldn't happen but handle gracefully
                parts = path.parts

            current = tree
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # It's a file
                    current[part] = {"type": "file", "path": str(path)}
                else:
                    # It's a directory
                    if part not in current:
                        current[part] = {"type": "dir", "children": {}}
                    current = current[part]["children"]

        # Render this tree
        lines.append(str(root))

        def render_tree(
            node: dict,
            prefix: str = "",
            is_last: bool = True,
        ) -> None:
            items = sorted(
                node.items(), key=lambda x: (x[1]["type"] == "file", x[0].lower())
            )

            for i, (name, info) in enumerate(items):
                is_last_item = i == len(items) - 1
                connector = "└── " if is_last_item else "├── "

                if info["type"] == "file":
                    # Check if attached
                    is_attached = info["path"] in attachment_set
                    marker = " attached" if is_attached else ""
                    lines.append(f"{prefix}{connector}{name}{marker}")
                else:
                    # Directory
                    lines.append(f"{prefix}{connector}{name}")
                    # Recurse
                    extension = "    " if is_last_item else "│   "
                    new_prefix = prefix + extension
                    render_tree(info["children"], new_prefix, is_last_item)

        render_tree(tree)

    return "\n".join(lines)
