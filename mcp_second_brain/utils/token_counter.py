from typing import Sequence
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
except Exception:
    _enc = None
def count_tokens(texts: Sequence[str]) -> int:
    return sum(len(_enc.encode(t)) if _enc else max(1, len(t)//4) for t in texts)
