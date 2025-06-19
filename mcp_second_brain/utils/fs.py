import mimetypes, os
from pathlib import Path
from typing import List, Set
def _text_file(p: Path) -> bool:
    if not p.is_file(): return False
    m, _ = mimetypes.guess_type(p.as_posix())
    if m and m.startswith("text/"): return True
    try: return b"\0" not in p.read_bytes() and p.stat().st_size < 5_000_000
    except Exception: return False
def gather_file_paths(items: List[str]) -> List[str]:
    seen: Set[str] = set(); out: List[str] = []
    for itm in items:
        p = Path(itm).expanduser().resolve()
        if not p.exists(): continue
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if _text_file(f) and (s := f.as_posix()) not in seen:
                    seen.add(s); out.append(s)
        elif _text_file(p):
            s = p.as_posix()
            if s not in seen: seen.add(s); out.append(s)
    return out
