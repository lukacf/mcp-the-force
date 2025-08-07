#!/usr/bin/env python3
"""Ultra-minimal git hook with zero external dependencies."""

import os
import subprocess
import json
import time


def record_commit_minimal():
    """Record commit with absolute minimal dependencies."""
    try:
        # Get commit info with timeouts
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=1
        )
        if result.returncode != 0:
            return False

        commit_sha = result.stdout.strip()

        # Lightweight payload
        payload = {
            "commit_sha": commit_sha,
            "timestamp": int(time.time()),
            "project": os.path.basename(os.getcwd()),
            "type": "commit",
        }

        # Simulate HTTP POST (no actual network call for benchmarking)
        _ = json.dumps(payload).encode("utf-8")
        return True

    except Exception:
        return False


if __name__ == "__main__":
    record_commit_minimal()
