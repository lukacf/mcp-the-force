#!/usr/bin/env python3
"""
Benchmark different file tree representation algorithms for token efficiency.
Tests 5 different approaches to minimize context usage in LLM prompts.
"""

import os
import time
import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Tuple
import logging
from collections import defaultdict

# For token counting
import tiktoken

logger = logging.getLogger(__name__)

# ==================== ORIGINAL IMPLEMENTATION ====================


def build_file_tree_original(
    all_paths: List[str],
    attachment_paths: List[str],
    root_path: Optional[Path] = None,
) -> str:
    """Original ASCII art implementation from the codebase."""
    if not all_paths:
        return "(empty)"

    # Normalize all paths and convert to Path objects
    all_paths_normalized = [Path(os.path.normpath(p)) for p in all_paths]
    attachment_set = {os.path.normpath(p) for p in attachment_paths}

    # Group paths by their common ancestors
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
            if len(all_paths_normalized) == 1:
                path_groups[path.parent] = [path]
            else:
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
                parts = path.parts

            current = tree
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    current[part] = {"type": "file", "path": str(path)}
                else:
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


# ==================== VERSION 1: GROK HEAVY ====================


def build_file_tree_v1_grok(
    all_paths: List[str],
    attachment_paths: List[str],
    root_path: Optional[Path] = None,
) -> str:
    """Version 1: Simple indented structure with (A)/(V) markers."""
    if not all_paths:
        return "(empty)"

    # Normalize paths (same as original)
    all_paths_normalized = [Path(os.path.normpath(p)) for p in all_paths]
    attachment_set = {os.path.normpath(p) for p in attachment_paths}

    # Group paths by common ancestors (same as original)
    path_groups: Dict[Path, List[Path]] = {}
    for path in all_paths_normalized:
        added = False
        for root in list(path_groups.keys()):
            try:
                path.relative_to(root)
                path_groups[root].append(path)
                added = True
                break
            except ValueError:
                try:
                    root.relative_to(path.parent)
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
            if len(all_paths_normalized) == 1:
                path_groups[path.parent] = [path]
            else:
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
                            pass
                if best_root not in path_groups:
                    path_groups[best_root] = []
                path_groups[best_root].append(path)

    # Build tree structure for each group (same as original)
    lines: List[str] = []
    for root, paths in sorted(path_groups.items()):
        if lines:
            lines.append("")
        tree: Dict[str, Any] = {}
        for path in paths:
            try:
                rel_path = path.relative_to(root)
                parts = rel_path.parts
            except ValueError:
                parts = path.parts
            current = tree
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    current[part] = {"type": "file", "path": str(path)}
                else:
                    if part not in current:
                        current[part] = {"type": "dir", "children": {}}
                    current = current[part]["children"]

        # Compact rendering
        lines.append(f"{root}/")  # Root as dir

        def render_tree(node: dict, level: int = 1) -> None:
            items = sorted(
                node.items(), key=lambda x: (x[1]["type"] == "file", x[0].lower())
            )
            for name, info in items:
                indent = "  " * level
                if info["type"] == "file":
                    marker = "(A)" if info["path"] in attachment_set else "(V)"
                    lines.append(f"{indent}{name} {marker}")
                else:
                    lines.append(f"{indent}{name}/")
                    render_tree(info["children"], level + 1)

        render_tree(tree)

    return "\n".join(lines)


# ==================== VERSION 2: O3 PRO ====================


def build_file_tree_v2_o3pro(
    all_paths: List[str],
    attachment_paths: List[str],
    root_path: Optional[Path] = None,
    max_files_per_dir: int = 10,
) -> str:
    """Version 2: Tab-indented with chain collapsing and summarization."""
    if not all_paths:
        return "(empty)"

    # Normalize
    all_p = [Path(os.path.normpath(p)).expanduser().resolve() for p in all_paths]
    attached_set = {str(Path(p).expanduser().resolve()) for p in attachment_paths}

    try:
        common_root = Path(os.path.commonpath([str(p) for p in all_p]))
        rel_paths = [p.relative_to(common_root) for p in all_p]
    except ValueError:
        # Different drives/mount points
        common_root = Path("/")
        rel_paths = all_p

    # Build nested dict
    tree: Dict = {}
    for rel_path in rel_paths:
        parts = rel_path.parts
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # File
                current.setdefault("__files__", []).append(rel_path.name)
            else:
                # Directory
                if part not in current:
                    current[part] = {}
                current = current[part]

    # Collapse linear chains
    def collapse(node: Dict) -> Dict:
        changed = True
        while changed:
            changed = False
            for key in list(node.keys()):
                if key == "__files__":
                    continue
                child = node[key]
                if not isinstance(child, dict):
                    continue

                sub_dirs = [k for k in child if k != "__files__"]
                if len(sub_dirs) == 1 and not child.get("__files__"):
                    # Collapse this chain
                    sub_key = sub_dirs[0]
                    grandchild = child[sub_key]
                    new_key = f"{key}/{sub_key}"
                    node[new_key] = grandchild
                    del node[key]
                    changed = True
                    break

            # Recursively collapse children
            for key, value in list(node.items()):
                if key != "__files__" and isinstance(value, dict):
                    collapse(value)
        return node

    tree = collapse(tree)

    # Render
    lines = ["Legend: *=attached ~=vector-store", f"ROOT: {common_root}"]

    def render_tree(node: Dict, prefix: str = ""):
        # Files first
        files = sorted(node.get("__files__", []))
        for i, name in enumerate(files[:max_files_per_dir]):
            full_path = str(common_root / prefix / name)
            flag = "*" if full_path in attached_set else "~"
            lines.append(f"\t{prefix}{name}{flag}")

        if len(files) > max_files_per_dir:
            lines.append(f"\t{prefix}…(+{len(files) - max_files_per_dir})")

        # Then directories
        dirs = sorted([k for k in node if k != "__files__"])
        for dir_name in dirs:
            lines.append(f"\t{prefix}{dir_name}/")
            render_tree(node[dir_name], f"{prefix}{dir_name}/")

    render_tree(tree)
    return "\n".join(lines)


# ==================== VERSION 3: GEMINI DENSETHINK ====================


def build_file_tree_v3_densetree(
    all_paths: List[str],
    attachment_paths: List[str],
    root_path: Optional[Path] = None,
) -> str:
    """Version 3: Ultra-compact DenseTree format with >|* delimiters."""
    if not all_paths:
        return "(empty)"

    # Normalize paths
    all_paths_normalized = [Path(os.path.normpath(p)) for p in all_paths]
    attachment_set = {os.path.normpath(p) for p in attachment_paths}

    # Find common root
    try:
        common_root = Path(os.path.commonpath([str(p) for p in all_paths_normalized]))
    except ValueError:
        common_root = Path("/")

    # Build nested structure
    tree: Dict[str, Any] = {}
    for path in all_paths_normalized:
        try:
            rel_path = path.relative_to(common_root)
            parts = rel_path.parts
        except ValueError:
            parts = path.parts

        if not parts:
            continue

        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # File
                current[part] = {"type": "file", "path": str(path)}
            else:
                # Directory
                if part not in current:
                    current[part] = {"type": "dir", "children": {}}
                elif current[part].get("type") != "dir":
                    current[part] = {"type": "dir", "children": {}}
                current = current[part]["children"]

    def render_densetree(node: Dict[str, Any]) -> str:
        """Render tree in ultra-compact format."""
        parts = []

        # Sort: directories first, then files
        items = sorted(
            node.items(), key=lambda x: (x[1].get("type") == "file", x[0].lower())
        )

        for name, info in items:
            if info.get("type") == "file":
                # File: name* if attached
                marker = "*" if info.get("path") in attachment_set else ""
                parts.append(f"{name}{marker}")
            elif info.get("type") == "dir":
                # Directory: name>children
                children_repr = render_densetree(info.get("children", {}))
                if children_repr:
                    parts.append(f"{name}>{children_repr}")
                else:
                    parts.append(name)

        return "|".join(parts)

    # Render with root
    legend = "DenseTree: >nesting |separation *attached"
    content = render_densetree(tree)
    if content:
        return f"{legend}\n{common_root}>{content}"
    else:
        return f"{legend}\n{common_root}"


# ==================== VERSION 4: ULTRATREE (O3 Pro Challenge) ====================

FILES_KEY = "__files__"


def build_file_tree_v4_ultratree(
    all_paths: List[str],
    attachment_paths: List[str],
    *,
    seq_min: int = 3,
    max_items_per_dir: int | None = 20,
) -> str:
    """
    Version 4: UltraTree with run-length compression and overflow markers.

    Parameters
    ----------
    all_paths           : every file path to include (absolute or relative)
    attachment_paths    : subset that is directly loadable (gets '*')
    seq_min             : minimum consecutive numbered files to compress
    max_items_per_dir   : after this many rendered items, summarise with '…(+N)'
    """
    if not all_paths:
        return "(empty)"

    attach_set = {os.path.normpath(p) for p in attachment_paths}
    root, tree = _build_structure_v4(all_paths)
    rendered = _render_tree_v4(
        tree, attach_set, Path(""), root, seq_min=seq_min, max_items=max_items_per_dir
    )
    return f"{root}>{rendered}" if str(root) not in ("/", ".") else rendered


def _build_structure_v4(all_paths: List[str]) -> Tuple[Path, Dict[str, Any]]:
    paths_norm = [Path(os.path.normpath(p)).expanduser().resolve() for p in all_paths]
    try:
        root_str = os.path.commonpath([str(p) for p in paths_norm]) or "/"
        root = Path(root_str)
    except ValueError:
        root = Path("/")

    tree: Dict[str, Any] = {}
    for p in paths_norm:
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p
        cur = tree
        for part in rel.parts[:-1]:
            cur = cur.setdefault(part, {})
        cur.setdefault(FILES_KEY, []).append(rel.parts[-1])
    return root, tree


# ---------- compression of numbered sequences ------------------------ #

_NUM_RE = re.compile(r"^(.*?)(\d+)(\.[^.]+)$")


def _compress_files_v4(
    files: List[str],
    path_func,
    attach_set: Set[str],
    seq_min: int,
    max_items: int | None,
) -> List[str]:
    files.sort()
    out, i, n = [], 0, len(files)

    def is_attached(name: str) -> bool:
        return path_func(name) in attach_set

    while i < n:
        name = files[i]
        if is_attached(name):
            out.append(f"{name}*")
            i += 1
            continue

        m = _NUM_RE.match(name)
        if not m:
            out.append(name)
            i += 1
            continue

        pre, num, suf = m.groups()
        seq = [int(num)]
        j = i + 1
        while j < n:
            nxt = files[j]
            if is_attached(nxt):
                break
            m2 = _NUM_RE.match(nxt)
            if not m2:
                break
            p2, num2, s2 = m2.groups()
            if p2 != pre or s2 != suf or int(num2) != seq[-1] + 1:
                break
            seq.append(int(num2))
            j += 1

        if len(seq) >= seq_min:
            out.append(f"{pre}[{seq[0]}-{seq[-1]}]{suf}")
            i = j
        else:
            out.append(name)
            i += 1

    if max_items is not None and len(out) > max_items:
        keep, rem = out[:max_items], len(out) - max_items
        keep.append(f"…(+{rem})")
        return keep
    return out


def _render_tree_v4(
    node: Dict[str, Any],
    attach_set: Set[str],
    prefix: Path,
    root: Path,
    *,
    seq_min: int,
    max_items: int | None,
    sib: str = "|",
    nest: str = ">",
) -> str:
    pieces: List[str] = []
    files = node.get(FILES_KEY, [])

    def full(fn: str) -> str:
        return str(root / prefix / fn)

    pieces.extend(_compress_files_v4(files, full, attach_set, seq_min, max_items))

    for dirname in sorted(k for k in node if k != FILES_KEY):
        child_str = _render_tree_v4(
            node[dirname],
            attach_set,
            prefix / dirname,
            root,
            seq_min=seq_min,
            max_items=max_items,
            sib=sib,
            nest=nest,
        )
        pieces.append(f"{dirname}{nest}{child_str}" if child_str else dirname)

    return sib.join(pieces)


# ==================== VERSION 5: FUSIONTREE (Gemini DeepThink Challenge) ====================

# A unique key to store files within a directory node, preventing name clashes
FILES_KEY_V5 = "__files__"

# Regex for splitting filenames into (prefix, number, suffix)
_NUM_RE_V5 = re.compile(r"^(.*?)(\d+)(?=\.\w+$|$)")


def build_file_tree_v5_fusiontree(
    all_paths: List[str],
    attachment_paths: List[str],
    *,
    seq_min: int = 3,
    max_items_per_dir: int | None = 15,
) -> str:
    """
    Version 5: FusionTree with advanced compression techniques.

    Features:
    - Nesting/Separation: `dir[item1,item2]`
    - Attached Flag: `file*`
    - Advanced Sequence Compression: `base[1-10].ext*<indices>`
    - Extension Grouping: `ext{file1,file2*}`
    - Prefix Factorization: `prefix{part1,part2*}`
    - Prioritized Truncation: `+N` (keeps attached files visible)
    """
    if not all_paths:
        return "(empty)"

    # Normalize paths and create a set of attached files for quick lookups
    attach_set = {os.path.normpath(p) for p in attachment_paths}

    # 1. Build the basic hierarchical dictionary from paths
    root, tree = _build_structure_v5(all_paths)

    # 2. Render the dictionary into the compressed string format
    rendered = _render_tree_v5(
        tree,
        attach_set,
        root,
        seq_min=seq_min,
        max_items=max_items_per_dir,
    )

    # 3. Format the final output with its root
    root_str = str(root)
    if root_str in ("/", ".") or not rendered:
        return rendered or root_str

    # Handle Windows drive letters correctly
    if re.match(r"^[A-Za-z]:\\?$", root_str):
        return f"{root_str.rstrip('\\\\')}" + f"[{rendered}]"

    return f"{root_str}[{rendered}]"


def _build_structure_v5(all_paths: List[str]) -> Tuple[Path, Dict[str, Any]]:
    """Builds a nested dictionary representing the file hierarchy."""
    if not all_paths:
        return Path("."), {}

    # Resolve paths to be absolute for reliable common path calculation
    paths_norm = [Path(os.path.normpath(p)).expanduser().resolve() for p in all_paths]

    try:
        # Find the deepest common directory to act as the root
        root_str = os.path.commonpath([str(p) for p in paths_norm])
        if os.path.isfile(root_str):
            root_str = os.path.dirname(root_str)
        root = Path(root_str)
    except ValueError:  # Happens on Windows with paths on different drives
        root = Path("/")  # Fallback for mixed-drive paths

    tree: Dict[str, Any] = {}
    for p in paths_norm:
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p  # Should not happen if commonpath is correct, but as a fallback

        cur = tree
        # Traverse path parts to create directory nodes
        for part in rel.parts[:-1]:
            cur = cur.setdefault(part, {})
        # Add the final filename to the special FILES_KEY list
        cur.setdefault(FILES_KEY_V5, []).append(rel.parts[-1])

    return root, tree


def _render_tree_v5(
    node: Dict[str, Any],
    attach_set: Set[str],
    current_path: Path,
    *,
    seq_min: int,
    max_items: int | None,
) -> str:
    """Recursively traverses the tree dictionary and renders it into a string."""

    # --- Step 1: Process Files ---
    raw_files = node.get(FILES_KEY_V5, [])
    # Create a list of (filename, is_attached) tuples
    files_with_status = [
        (name, str(current_path / name) in attach_set) for name in raw_files
    ]

    # Apply compression layers to the file list
    compressed_files = _compress_sequences_v5(files_with_status, seq_min)
    grouped_by_ext = _group_by_extension_v5(compressed_files)
    factorized_files = _factor_prefixes_v5(grouped_by_ext)

    # --- Step 2: Process Directories ---
    dir_items = []
    # Sort directory names for consistent output
    dir_names = sorted([k for k in node if k != FILES_KEY_V5])
    for dirname in dir_names:
        # Recursively render child directories
        child_str = _render_tree_v5(
            node[dirname],
            attach_set,
            current_path / dirname,
            seq_min=seq_min,
            max_items=max_items,
        )
        if child_str:
            dir_items.append(f"{dirname}[{child_str}]")
        else:
            dir_items.append(dirname)  # Handle empty directories

    factorized_dirs = _factor_prefixes_v5(dir_items)

    # --- Step 3: Combine and Truncate ---
    all_items = factorized_dirs + factorized_files
    truncated_items = _truncate_list_v5(all_items, max_items)

    return ",".join(truncated_items)


def _compress_sequences_v5(
    files_with_status: List[Tuple[str, bool]], seq_min: int
) -> List[str]:
    """Compresses numeric sequences, e.g., 'img1.png, img2.png' -> 'img[1-2].png'."""
    if not files_with_status:
        return []

    files_with_status.sort()
    output: List[str] = []
    i = 0
    while i < len(files_with_status):
        name, is_attached = files_with_status[i]
        match = _NUM_RE_V5.match(name)
        if not match:
            output.append(f"{name}*" if is_attached else name)
            i += 1
            continue

        prefix, num_str = match.groups()
        # Extract suffix (everything after the number)
        suffix = name[len(prefix) + len(num_str) :]

        # Start a potential sequence
        seq = [(int(num_str), is_attached)]
        j = i + 1
        while j < len(files_with_status):
            next_name, next_attached = files_with_status[j]
            next_match = _NUM_RE_V5.match(next_name)
            if not next_match:
                break

            next_prefix, next_num_str = next_match.groups()
            next_suffix = next_name[len(next_prefix) + len(next_num_str) :]

            # Check if the file is part of the sequence
            if (
                next_prefix == prefix
                and next_suffix == suffix
                and int(next_num_str) == seq[-1][0] + 1
            ):
                seq.append((int(next_num_str), next_attached))
                j += 1
            else:
                break

        # If the sequence is long enough, compress it
        if len(seq) >= seq_min:
            start_num, end_num = seq[0][0], seq[-1][0]
            # Find indices of attached files within the sequence
            attached_indices = [k + 1 for k, item in enumerate(seq) if item[1]]

            base = f"{prefix}[{start_num}-{end_num}]{suffix}"
            if attached_indices:
                # Format: base*<1,3,4>
                indices_str = ",".join(map(str, attached_indices))
                output.append(f"{base}*<{indices_str}>")
            else:
                output.append(base)
            i = j  # Move pointer past the consumed sequence
        else:
            # Sequence not long enough, add the first file and continue
            output.append(f"{name}*" if is_attached else name)
            i += 1

    return output


def _group_by_extension_v5(items: List[str]) -> List[str]:
    """Groups files by extension, e.g., 'a.py, b.py' -> 'py{a,b}'."""
    ext_map = defaultdict(list)
    others = []
    for item in items:
        # Don't group items that are already complex (sequences, factorizations)
        if any(c in item for c in "[]{}"):
            others.append(item)
            continue

        base, dot, ext = item.rpartition(".")
        if dot and base and not ext.isdigit():  # Ensure it's a real extension
            is_attached = base.endswith("*")
            clean_base = base.rstrip("*")
            ext_map[ext].append(f"{clean_base}{'*' if is_attached else ''}")
        else:
            others.append(item)

    # Format the groups
    for ext, files in ext_map.items():
        if len(files) > 1:
            # Sort files within the group for consistency
            files.sort()
            others.append(f"{ext}{{{','.join(files)}}}")
        else:  # Not worth grouping a single file
            base = files[0]
            is_attached = base.endswith("*")
            clean_base = base.rstrip("*")
            others.append(f"{clean_base}.{ext}{'*' if is_attached else ''}")

    others.sort()
    return others


def _factor_prefixes_v5(items: List[str]) -> List[str]:
    """Factors common prefixes, e.g., 'ab,ac' -> 'a{b,c}'."""
    if len(items) < 2:
        return items

    items.sort()
    prefix_map = defaultdict(list)

    # Use a simple separator like '_' or '-' for splitting
    for item in items:
        # Avoid re-processing complex items
        if any(c in item for c in "[]{}"):
            prefix_map[item].append("")  # Add to its own group
            continue

        parts = re.split(r"([_-])", item, 1)
        if len(parts) > 1:
            prefix = parts[0]
            # Don't factor tiny prefixes
            if len(prefix) > 2:
                suffix = "".join(parts[1:])
                prefix_map[prefix].append(suffix)
            else:
                prefix_map[item].append("")
        else:
            prefix_map[item].append("")

    output = []
    for prefix, suffixes in prefix_map.items():
        # Clean empty strings that result from non-split items
        suffixes = [s for s in suffixes if s]
        if len(suffixes) > 1:
            # Sort for consistent output
            suffixes.sort()
            output.append(f"{prefix}{{{','.join(suffixes)}}}")
        else:
            output.append(prefix + (suffixes[0] if suffixes else ""))

    output.sort()
    return output


def _truncate_list_v5(items: List[str], max_items: int | None) -> List[str]:
    """Truncates a list, prioritizing attached files and directories."""
    if max_items is None or len(items) <= max_items:
        return items

    # Prioritize directories and attached files
    priority_items = [item for item in items if "[" in item or "*" in item]
    other_items = [item for item in items if item not in priority_items]

    # Fill the list with priority items first
    keep = priority_items[:max_items]

    # If there's space left, fill with other items
    if len(keep) < max_items:
        keep.extend(other_items[: max_items - len(keep)])

    # Sort the final list to maintain order
    keep.sort()

    remaining_count = len(items) - len(keep)
    if remaining_count > 0:
        keep.append(f"+{remaining_count}")

    return keep


# ==================== BENCHMARKING ====================


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken (GPT-4 encoding)."""
    encoding = tiktoken.encoding_for_model("gpt-4")
    return len(encoding.encode(text))


def generate_test_data():
    """Generate realistic test data sets of varying sizes."""
    test_cases = []

    # Small project (10 files)
    small_paths = [
        "/project/README.md",
        "/project/src/main.py",
        "/project/src/utils.py",
        "/project/tests/test_main.py",
        "/project/tests/test_utils.py",
        "/project/docs/api.md",
        "/project/config.yaml",
        "/project/requirements.txt",
        "/project/.gitignore",
        "/project/Makefile",
    ]
    small_attached = [
        "/project/README.md",
        "/project/src/main.py",
        "/project/config.yaml",
    ]
    test_cases.append(("Small (10 files)", small_paths, small_attached))

    # Medium project (50 files)
    medium_paths = []
    medium_attached = []
    for i in range(50):
        if i < 20:
            path = f"/project/src/module{i//5}/file{i}.py"
        elif i < 35:
            path = f"/project/tests/test_module{(i-20)//3}/test{i}.py"
        else:
            path = f"/project/docs/section{(i-35)//5}/doc{i}.md"
        medium_paths.append(path)
        if i % 3 == 0:  # 1/3 attached
            medium_attached.append(path)
    test_cases.append(("Medium (50 files)", medium_paths, medium_attached))

    # Large project (200 files)
    large_paths = []
    large_attached = []
    for i in range(200):
        if i < 100:
            path = f"/bigproject/src/module{i//10}/submodule{i//5}/file{i}.py"
        elif i < 150:
            path = f"/bigproject/tests/unit/module{(i-100)//10}/test{i}.py"
        else:
            path = f"/bigproject/docs/section{(i-150)//10}/subsection{(i-150)//5}/doc{i}.md"
        large_paths.append(path)
        if i % 4 == 0:  # 1/4 attached
            large_attached.append(path)
    test_cases.append(("Large (200 files)", large_paths, large_attached))

    # Special numbered files test case (ideal for UltraTree)
    numbered_paths = []
    numbered_attached = []
    # Add numbered image sequences
    for i in range(100):
        path = f"/project/assets/images/frame{i:04d}.png"
        numbered_paths.append(path)
        if i % 10 == 0:  # Every 10th image attached
            numbered_attached.append(path)

    # Add numbered test files
    for i in range(50):
        path = f"/project/tests/integration/test{i:03d}.py"
        numbered_paths.append(path)
        if i % 5 == 0:  # Every 5th test attached
            numbered_attached.append(path)

    # Add some regular files
    numbered_paths.extend(
        ["/project/README.md", "/project/src/main.py", "/project/config.yaml"]
    )
    numbered_attached.extend(["/project/README.md", "/project/src/main.py"])

    test_cases.append(("Numbered (153 files)", numbered_paths, numbered_attached))

    # Real codebase 1: Current MCP project
    try:
        mcp_paths = []
        mcp_attached = []
        mcp_root = Path("/Users/luka/src/cc/mcp-the-force")

        # Walk the directory and collect Python/config files (typical context files)
        for root, dirs, files in os.walk(mcp_root):
            # Skip common ignore patterns
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in ["__pycache__", "node_modules", ".git", "dist", "build"]
            ]

            for file in files:
                if file.startswith(".") and file not in [".gitignore", ".env.example"]:
                    continue

                # Include typical source/config files
                if any(
                    file.endswith(ext)
                    for ext in [
                        ".py",
                        ".yaml",
                        ".yml",
                        ".toml",
                        ".md",
                        ".txt",
                        ".json",
                        ".cfg",
                        ".ini",
                    ]
                ):
                    full_path = os.path.join(root, file)
                    mcp_paths.append(full_path)

                    # Mark some files as "attached" (key source files)
                    if any(
                        pattern in full_path
                        for pattern in [
                            "/mcp_the_force/",
                            "setup.py",
                            "pyproject.toml",
                            "README",
                            "Makefile",
                        ]
                    ):
                        mcp_attached.append(full_path)

        if mcp_paths:  # Only add if we found files
            test_cases.append(
                (f"Real: MCP ({len(mcp_paths)} files)", mcp_paths, mcp_attached)
            )
    except Exception as e:
        print(f"Warning: Could not load MCP codebase: {e}")

    # Real codebase 2: Life Tales Generator
    try:
        ltg_paths = []
        ltg_attached = []
        ltg_root = Path("/Users/luka/Docs/code/misc/life-tales-generator")

        if ltg_root.exists():
            for root, dirs, files in os.walk(ltg_root):
                # Skip common ignore patterns
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d
                    not in [
                        "__pycache__",
                        "node_modules",
                        ".git",
                        "dist",
                        "build",
                        ".next",
                    ]
                ]

                for file in files:
                    if file.startswith(".") and file not in [
                        ".gitignore",
                        ".env.example",
                        ".env.local",
                    ]:
                        continue

                    # Include typical web dev files
                    if any(
                        file.endswith(ext)
                        for ext in [
                            ".ts",
                            ".tsx",
                            ".js",
                            ".jsx",
                            ".py",
                            ".yaml",
                            ".yml",
                            ".json",
                            ".md",
                            ".txt",
                            ".css",
                            ".scss",
                            ".html",
                        ]
                    ):
                        full_path = os.path.join(root, file)
                        ltg_paths.append(full_path)

                        # Mark some files as "attached" (main source files)
                        if any(
                            pattern in full_path
                            for pattern in [
                                "/src/",
                                "/components/",
                                "/pages/",
                                "/lib/",
                                "package.json",
                                "README",
                                "next.config",
                            ]
                        ):
                            ltg_attached.append(full_path)

            if ltg_paths:  # Only add if we found files
                test_cases.append(
                    (
                        f"Real: LifeTales ({len(ltg_paths)} files)",
                        ltg_paths,
                        ltg_attached,
                    )
                )
    except Exception as e:
        print(f"Warning: Could not load Life Tales Generator codebase: {e}")

    # Real codebase 3: Candy Crush Saga
    try:
        ccs_base_path = "/Users/luka/src/candycrushsaga"
        if os.path.exists(ccs_base_path):
            print(f"Loading Candy Crush Saga codebase from {ccs_base_path}...")
            ccs_paths = []
            ccs_attached = []

            # Find all source code files
            for root, dirs, files in os.walk(ccs_base_path):
                # Skip certain large directories to keep reasonable size
                dirs_to_skip = [
                    "bazel-bin",
                    "bazel-out",
                    "bazel-testlogs",
                    "bazel-candycrushsaga",
                    "build_output",
                    "res_output",
                    "res_cache",
                    "atlas_images",
                ]
                dirs[:] = [d for d in dirs if d not in dirs_to_skip]

                for file in files:
                    # Include all source code files
                    if any(
                        file.endswith(ext)
                        for ext in [
                            ".cpp",
                            ".h",
                            ".hpp",
                            ".c",
                            ".cc",
                            ".cxx",
                            ".py",
                            ".js",
                            ".ts",
                            ".tsx",
                            ".jsx",
                            ".java",
                            ".kt",
                            ".swift",
                            ".rs",
                            ".go",
                            ".cs",
                            ".php",
                            ".rb",
                            ".scala",
                            ".pl",
                            ".sh",
                            ".bat",
                            ".ps1",
                        ]
                    ):
                        full_path = os.path.join(root, file)
                        ccs_paths.append(full_path)

                        # Mark core source files as "attached" (main implementation)
                        if any(
                            pattern in full_path
                            for pattern in [
                                "/candycrushsaga/",
                                "/components/",
                                "/python_tools/",
                                "/bz-tools/",
                                "CMakeLists.txt",
                                "BUILD",
                                "Makefile",
                            ]
                        ):
                            ccs_attached.append(full_path)

            if ccs_paths:  # Only add if we found files
                test_cases.append(
                    (
                        f"Real: CandyCrush ({len(ccs_paths)} files)",
                        ccs_paths,
                        ccs_attached,
                    )
                )
                print(
                    f"Loaded {len(ccs_paths)} source files, {len(ccs_attached)} marked as attached"
                )
    except Exception as e:
        print(f"Warning: Could not load Candy Crush Saga codebase: {e}")

    return test_cases


def benchmark_implementations():
    """Run comprehensive benchmark of all implementations."""
    # Import advanced algorithms
    from quarktree import build_file_tree_quarktree
    from neutrinotree import build_file_tree_neutrinotree
    from autotree import build_file_tree_autotree, build_file_tree_autotree_fast

    implementations = [
        ("Original ASCII", build_file_tree_original),
        ("V1 Grok Heavy", build_file_tree_v1_grok),
        ("V2 O3 Pro", build_file_tree_v2_o3pro),
        ("V3 DenseTree", build_file_tree_v3_densetree),
        ("V4 UltraTree", build_file_tree_v4_ultratree),
        ("V5 FusionTree", build_file_tree_v5_fusiontree),
        (
            "V6 QuarkTree",
            lambda paths, attachments, **kwargs: build_file_tree_quarktree(
                paths,
                attachments,
                seq_min=kwargs.get("seq_min", 3),
                max_items_per_dir=kwargs.get("max_items_per_dir", 15),
            ),
        ),
        (
            "V7 NeutrinoTree",
            lambda paths, attachments, **kwargs: build_file_tree_neutrinotree(
                paths,
                attachments,
                seq_min=kwargs.get("seq_min", 3),
                seq_gap=kwargs.get("seq_gap", 1),
                max_items_per_dir=kwargs.get("max_items_per_dir", 15),
            ),
        ),
        (
            "V8 AutoTree",
            lambda paths, attachments, **kwargs: build_file_tree_autotree(
                paths,
                attachments,
                seq_min=kwargs.get("seq_min", 3),
                seq_gap=kwargs.get("seq_gap", 1),
                max_items_per_dir=kwargs.get("max_items_per_dir", 15),
                bench_timeout_ms=200,
            ),
        ),
        (
            "V9 AutoTree-Fast",
            lambda paths, attachments, **kwargs: build_file_tree_autotree_fast(
                paths,
                attachments,
                seq_min=kwargs.get("seq_min", 3),
                seq_gap=kwargs.get("seq_gap", 1),
                max_items_per_dir=kwargs.get("max_items_per_dir", 15),
            ),
        ),
    ]

    test_cases = generate_test_data()

    print("=" * 80)
    print("FILE TREE REPRESENTATION BENCHMARK")
    print("=" * 80)
    print()

    results = {}

    for case_name, all_paths, attachment_paths in test_cases:
        print(f"Test Case: {case_name}")
        print("-" * 40)

        case_results = {}

        for impl_name, impl_func in implementations:
            # Time the implementation
            start_time = time.time()
            try:
                output = impl_func(all_paths, attachment_paths)
                end_time = time.time()

                # Count metrics
                char_count = len(output)
                token_count = count_tokens(output)
                line_count = output.count("\n") + 1
                exec_time = (end_time - start_time) * 1000  # ms

                case_results[impl_name] = {
                    "tokens": token_count,
                    "chars": char_count,
                    "lines": line_count,
                    "time_ms": exec_time,
                    "output": output,
                }

                print(
                    f"{impl_name:15} | {token_count:4d} tokens | {char_count:4d} chars | {line_count:2d} lines | {exec_time:5.1f}ms"
                )

            except Exception as e:
                print(f"{impl_name:15} | ERROR: {e}")
                case_results[impl_name] = {"error": str(e)}

        results[case_name] = case_results
        print()

    # Summary analysis
    print("SUMMARY ANALYSIS")
    print("=" * 80)

    for case_name, case_results in results.items():
        print(f"\n{case_name}:")

        # Find baseline (original)
        if (
            "Original ASCII" in case_results
            and "tokens" in case_results["Original ASCII"]
        ):
            baseline_tokens = case_results["Original ASCII"]["tokens"]

            token_savings = []
            for impl_name, metrics in case_results.items():
                if "tokens" in metrics:
                    tokens = metrics["tokens"]
                    savings = ((baseline_tokens - tokens) / baseline_tokens) * 100
                    token_savings.append((impl_name, tokens, savings))

            # Sort by token count (ascending)
            token_savings.sort(key=lambda x: x[1])

            print("  Token efficiency ranking:")
            for i, (impl_name, tokens, savings) in enumerate(token_savings):
                if impl_name == "Original ASCII":
                    print(f"    {i+1}. {impl_name:15} | {tokens:4d} tokens | baseline")
                else:
                    print(
                        f"    {i+1}. {impl_name:15} | {tokens:4d} tokens | {savings:+5.1f}% vs baseline"
                    )

    return results


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.WARNING)  # Suppress debug output

    # Run benchmark
    results = benchmark_implementations()

    # Show sample outputs for the smallest test case
    print("\n" + "=" * 80)
    print("SAMPLE OUTPUTS (Small test case)")
    print("=" * 80)

    if "Small (10 files)" in results:
        case_results = results["Small (10 files)"]
        for impl_name, metrics in case_results.items():
            if "output" in metrics:
                print(f"\n{impl_name}:")
                print("-" * 20)
                print(metrics["output"])
                print(f"({metrics['tokens']} tokens, {metrics['chars']} chars)")
