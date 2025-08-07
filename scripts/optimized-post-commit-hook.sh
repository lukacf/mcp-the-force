#!/bin/sh
# Ultra-optimized post-commit hook with multiple performance strategies

# Performance optimization flags
export PYTHONDONTWRITEBYTECODE=1  # Skip .pyc creation
export PYTHONOPTIMIZE=1           # Enable Python optimizations
export PYTHONHASHSEED=0           # Deterministic hashing
export PYTHONNODEBUGRANGES=1      # Disable debug info (Python 3.13+)
export UV_CACHE_DIR="${HOME}/.cache/uv"  # Persistent cache

# Get git root efficiently
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$GIT_ROOT" ]; then
    exit 0  # Not a git repo
fi

cd "$GIT_ROOT" || exit 0

# Strategy 1: Try optimized fast_commit module (fastest ~50-150ms)
if [ -f "mcp_the_force/history/fast_commit.py" ]; then
    {
        # Use direct Python with sys.path manipulation (fastest)
        exec python3 -c "
import sys, os
sys.path.insert(0, '.')
os.environ.update({
    'PYTHONDONTWRITEBYTECODE': '1',
    'PYTHONOPTIMIZE': '1', 
    'PYTHONHASHSEED': '0'
})
from mcp_the_force.history.fast_commit import record_commit_fast
record_commit_fast()
" 2>/dev/null
    } &
    exit 0
fi

# Strategy 2: Try standalone optimized script (medium ~100-250ms)  
if [ -f "scripts/optimized-commit-hook.py" ]; then
    {
        exec python3 "scripts/optimized-commit-hook.py" 2>/dev/null
    } &
    exit 0
fi

# Strategy 3: Use uv with optimizations (slower ~200-400ms)
if command -v uv >/dev/null 2>&1; then
    {
        # Use uv with performance flags
        exec env VIRTUAL_ENV= uv run \
            --no-sync \
            --python python3 \
            -m mcp_the_force.history.commit 2>/dev/null
    } &
    exit 0
fi

# Strategy 4: Fallback to standard python module (slowest ~300-600ms)
{
    exec python3 -m mcp_the_force.history.commit 2>/dev/null
} &