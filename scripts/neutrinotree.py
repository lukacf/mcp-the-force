"""
NeutrinoTree v1.0  –  The 'try‑everything‑pick‑shortest' file‑tree encoder
API is identical to FusionTree's build_file_tree_fusiontree().
"""

from __future__ import annotations
import os
import re
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from collections import defaultdict

try:
    import tiktoken

    _enc = tiktoken.get_encoding("o200k_base")

    def _toklen(s: str) -> int:
        return len(_enc.encode(s))

except Exception:  # pragma: no cover

    def _toklen(s: str) -> int:
        return len(s)  # fallback: character length ≈ token count


FILES_KEY = "__files__"
NUM_RE = re.compile(r"^(.*?)(\d+)(?=\.\w+$|$)")

# ---------------------------------------------------------------------------


def build_file_tree_neutrinotree(
    all_paths: List[str],
    attachment_paths: List[str],
    *,
    seq_min: int = 3,
    seq_gap: int = 1,  # merge ranges separated by <= gap
    max_items_per_dir: int | None = 15,
) -> str:
    if not all_paths:
        return "(empty)"

    attach = {os.path.normpath(p) for p in attachment_paths}
    root, tree = _build_structure(all_paths)
    body = _render(
        tree,
        attach,
        root,
        seq_min=seq_min,
        seq_gap=seq_gap,
        max_items=max_items_per_dir,
    )
    r = str(root)
    if r in ("/", ".") or not body:
        return body or r
    if re.match(r"^[A-Za-z]:\\?$", r):
        return f"{r.rstrip('\\')}[{body}]"
    return f"{r}[{body}]"


# ---------------------------------------------------------------------------


def _build_structure(all_paths: List[str]) -> Tuple[Path, Dict[str, Any]]:
    abs_paths = [Path(os.path.normpath(p)).expanduser().resolve() for p in all_paths]
    try:
        root = Path(os.path.commonpath([str(p) for p in abs_paths]))
        if root.is_file():
            root = root.parent
    except ValueError:
        root = Path("/")
    tree: Dict[str, Any] = {}
    for p in abs_paths:
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p
        cur = tree
        for part in rel.parts[:-1]:
            cur = cur.setdefault(part, {})
        cur.setdefault(FILES_KEY, []).append(rel.parts[-1])
    return root, tree


# ---------------------------------------------------------------------------


def _render(
    node: Dict[str, Any],
    attach: Set[str],
    cwd: Path,
    *,
    seq_min: int,
    seq_gap: int,
    max_items: int | None,
) -> str:
    # -------- files --------------------------------------------------------
    files_raw = node.get(FILES_KEY, [])
    files_status = [(f, str(cwd / f) in attach) for f in files_raw]
    files_simple = _compress_numeric(files_status, seq_min, seq_gap)

    # -------- directories --------------------------------------------------
    dir_names = sorted(k for k in node if k != FILES_KEY)
    dir_encs = []
    for d in dir_names:
        if node[d]:
            child_content = _render(
                node[d],
                attach,
                cwd / d,
                seq_min=seq_min,
                seq_gap=seq_gap,
                max_items=max_items,
            )
            dir_encs.append(f"{d}[{child_content}]")
        else:
            dir_encs.append(d)

    # -------- combine & optimise ------------------------------------------
    siblings = dir_encs + files_simple
    encoded = _shortest_encoding(siblings)

    if max_items and len(encoded) > max_items:
        digest = hashlib.sha1(",".join(encoded).encode()).hexdigest()[:4]
        encoded = encoded[:max_items] + [f"#{digest}"]

    return ",".join(encoded)


# ---------------------------------------------------------------------------
#  Encoding strategies                                                       #
# ---------------------------------------------------------------------------


def _compress_numeric(
    files: List[Tuple[str, bool]], seq_min: int, seq_gap: int
) -> List[str]:
    if not files:
        return []
    files.sort()
    out, i = [], 0
    N = len(files)

    while i < N:
        name, is_star = files[i]
        m = NUM_RE.match(name)
        if not m:
            out.append(f"{name}*" if is_star else name)
            i += 1
            continue

        pre, num = m.groups()
        suf = name[len(pre) + len(num) :]
        seq = [(int(num), is_star)]
        j = i + 1
        while j < N:
            n2, st2 = files[j]
            m2 = NUM_RE.match(n2)
            if not m2:
                break
            p2, n2_num = m2.groups()
            s2 = n2[len(p2) + len(n2_num) :]
            if p2 != pre or s2 != suf:
                break
            if int(n2_num) - seq[-1][0] > seq_gap + 1:
                break
            seq.append((int(n2_num), st2))
            j += 1

        if len(seq) >= seq_min:
            ranges, star_idx = _seq_to_range(seq)
            base = f"{pre}[{ranges}]{suf}"
            if star_idx:
                base += f"*<{star_idx}>"
            out.append(base)
            i = j
        else:
            out.append(f"{name}*" if is_star else name)
            i += 1
    return out


def _seq_to_range(entries: List[Tuple[int, bool]]) -> Tuple[str, str]:
    # ranges
    nums = [n for n, _ in entries]
    nums.sort()
    merged, start = [], nums[0]
    for idx in range(1, len(nums)):
        if nums[idx] != nums[idx - 1] + 1:
            merged.append((start, nums[idx - 1]))
            start = nums[idx]
    merged.append((start, nums[-1]))
    range_str = ",".join(f"{a}-{b}" if a != b else f"{a}" for a, b in merged)

    # star indexes relative to start of seq (1‑based)
    stars = [i + 1 for i, (_, s) in enumerate(entries) if s]
    star_str = ",".join(_ranges_from_sorted(stars)) if stars else ""
    return range_str, star_str


def _ranges_from_sorted(nums: List[int]) -> List[str]:
    if not nums:
        return []
    out, start = [], nums[0]
    for idx in range(1, len(nums)):
        if nums[idx] != nums[idx - 1] + 1:
            out.append(
                f"{start}-{nums[idx-1]}" if start != nums[idx - 1] else f"{start}"
            )
            start = nums[idx]
    out.append(f"{start}-{nums[-1]}" if start != nums[-1] else f"{start}")
    return out


# ---------------------------------------------------------------------------


def _shortest_encoding(items: List[str]) -> List[str]:
    """Return whichever of three strategies is shortest."""
    if len(items) < 2:
        return items

    # Strategy A: ungrouped (status quo)
    ungrouped = items

    # Strategy B: extension grouping
    ext_group = _group_by_extension(items)

    # Strategy C: prefix factorisation
    pre_group = _factor_prefix(items)

    candidates = [ungrouped, ext_group, pre_group]
    best = min(candidates, key=lambda x: _toklen(",".join(x)))
    return best


# ---------------------------------------------------------------------------


def _group_by_extension(items: List[str]) -> List[str]:
    ext_map: Dict[str, List[str]] = defaultdict(list)
    misc: List[str] = []
    for it in items:
        if any(c in it for c in "[]{}()#"):  # already complex => leave
            misc.append(it)
            continue
        root, dot, ext = it.rpartition(".")
        if dot and root and not root[-1].isdigit():
            star = root.endswith("*")
            ext_map[ext].append(root.rstrip("*") + ("*" if star else ""))
        else:
            misc.append(it)

    for ext, arr in list(ext_map.items()):
        if len(arr) == 1:
            misc.append(f"{arr[0]}.{ext}")
            del ext_map[ext]

    out = misc + [
        f"{ext}{{{','.join(sorted(v))}}}" for ext, v in sorted(ext_map.items())
    ]
    out.sort()
    return out


def _factor_prefix(items: List[str]) -> List[str]:
    pre_map: Dict[str, List[str]] = defaultdict(list)
    others: List[str] = []
    pattern = re.compile(r"(.+?)[_-]([^_-]+)$")
    for it in items:
        if any(c in it for c in "[]{}()#"):
            others.append(it)
            continue
        m = pattern.match(it)
        if m and len(m.group(1)) > 2:
            pre, suf = m.groups()
            pre_map[pre].append(suf)
        else:
            others.append(it)

    for pre, suf in list(pre_map.items()):
        if len(suf) == 1:
            others.append(f"{pre}_{suf[0]}")
            del pre_map[pre]

    out = others + [
        f"{pre}{{{','.join(sorted(suf))}}}" for pre, suf in sorted(pre_map.items())
    ]
    out.sort()
    return out
