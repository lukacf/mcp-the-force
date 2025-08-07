#!/usr/bin/env python3
"""Ultra-fast git post-commit hook optimized for frequent execution.

Performance optimizations:
- Direct shebang (no uv overhead)
- Lazy imports
- Minimal dependencies loaded upfront
- Connection pooling for HTTP requests
- Cached configuration
- Optimized git command execution
"""

import os
import sys
import time
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add the project to Python path efficiently
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Global cache for expensive operations
_config_cache = None
_http_session = None
_settings_cache = None


def _git_command_fast(args: List[str]) -> Optional[str]:
    """Execute git command with minimal overhead."""
    try:
        # Use subprocess.run with optimized parameters
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,  # Prevent hanging
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None


def _get_http_session():
    """Get or create cached HTTP session for connection reuse."""
    global _http_session
    if _http_session is None:
        # Lazy import to avoid startup cost
        import requests

        _http_session = requests.Session()
        # Optimize for frequent small requests
        _http_session.headers.update(
            {"Connection": "keep-alive", "User-Agent": "mcp-the-force-hook/1.0"}
        )
    return _http_session


def _get_cached_settings():
    """Get cached settings to avoid repeated YAML parsing."""
    global _settings_cache
    if _settings_cache is None:
        # Lazy import configuration
        try:
            from mcp_the_force.config import get_settings

            _settings_cache = get_settings()
        except Exception:
            # Fallback minimal config
            _settings_cache = type(
                "Settings",
                (),
                {
                    "history_max_files_per_commit": 50,
                    "session_db_path": ".mcp-the-force/sessions.sqlite3",
                    "history_session_cutoff_hours": 2,
                },
            )()
    return _settings_cache


def _get_recent_session_fast() -> Optional[str]:
    """Fast session lookup with minimal overhead."""
    try:
        settings = _get_cached_settings()
        db_path = Path(settings.session_db_path)
        if not db_path.exists():
            return None

        # Use sqlite3 with optimized connection
        import sqlite3

        cutoff = int(time.time()) - (settings.history_session_cutoff_hours * 3600)

        with sqlite3.connect(str(db_path), timeout=1.0) as db:
            # Optimized query with index usage
            cur = db.execute(
                "SELECT session_id FROM unified_sessions WHERE updated_at > ? ORDER BY updated_at DESC LIMIT 1",
                (cutoff,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _create_commit_payload(commit_sha: str) -> Dict[str, Any]:
    """Create commit payload with minimal git operations."""
    # Batch git commands for efficiency
    commands = {
        "parent": ["rev-parse", f"{commit_sha}~1"],
        "branch": ["branch", "--show-current"],
        "message": ["log", "-1", "--pretty=%B", commit_sha],
        "files": ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha],
        "timestamp": ["show", "-s", "--format=%ct", commit_sha],
        "stats": ["show", "--stat", commit_sha],
    }

    git_data = {}
    for key, args in commands.items():
        git_data[key] = _git_command_fast(args) or ""

    # Process results
    parent_sha = git_data["parent"] or "root"
    branch = git_data["branch"] or "main"
    commit_message = git_data["message"]
    changed_files = [f for f in git_data["files"].split("\n") if f]
    timestamp = (
        int(git_data["timestamp"])
        if git_data["timestamp"].isdigit()
        else int(time.time())
    )

    settings = _get_cached_settings()
    session_id = _get_recent_session_fast()

    # Create minimal summary
    summary = f"""## Git Commit: {commit_sha[:8]}

**Date**: {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(timestamp))}

### Commit Message
{commit_message}

### Files Modified ({len(changed_files)} files)
{chr(10).join(f"- {f}" for f in changed_files[:10])}
{f"... and {len(changed_files) - 10} more files" if len(changed_files) > 10 else ""}
"""

    return {
        "content": summary,
        "commit_message": commit_message,
        "metadata": {
            "type": "commit",
            "commit_sha": commit_sha,
            "parent_sha": parent_sha,
            "branch": branch,
            "timestamp": timestamp,
            "files_changed": changed_files[: settings.history_max_files_per_commit],
            "session_id": session_id,
        },
    }


def _submit_to_vector_store_fast(payload: Dict[str, Any], commit_sha: str) -> bool:
    """Submit to vector store with minimal async overhead."""
    try:
        # Create temporary file efficiently
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f"_commit_{commit_sha[:8]}.json", delete=False
        ) as tmp_file:
            json.dump(payload, tmp_file, separators=(",", ":"))  # Compact JSON
            tmp_path = tmp_file.name

        try:
            # Use thread-based approach instead of async for better performance
            import concurrent.futures
            import asyncio

            def sync_upload():
                """Synchronous wrapper for async upload."""
                # Lazy import heavy dependencies only when needed
                from mcp_the_force.vectorstores.manager import vector_store_manager
                from mcp_the_force.vectorstores.protocol import VSFile
                from mcp_the_force.history.config import get_history_config

                # Read file content
                with open(tmp_path, "r") as f:
                    content = f.read()

                # Create VSFile
                vs_file = VSFile(
                    path=f"commits/{commit_sha}.json",
                    content=content,
                    metadata={"type": "commit", "sha": commit_sha},
                )

                # Get config and store
                config = get_history_config()
                store_id = config.get_active_commit_store()

                # Use existing event loop or create new one efficiently
                try:
                    loop = asyncio.get_running_loop()
                    # We're in an event loop, use create_task
                    return False  # Skip for now in async context
                except RuntimeError:
                    # No running loop, create minimal one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # Get client and upload
                        client = vector_store_manager._get_client(
                            vector_store_manager.provider
                        )
                        store = loop.run_until_complete(client.get(store_id))
                        loop.run_until_complete(store.add_files([vs_file]))
                        config.increment_commit_count()
                        return True
                    finally:
                        loop.close()

            # Execute with timeout
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(sync_upload)
                return future.result(timeout=5.0)  # 5 second timeout

        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)

    except Exception as e:
        # Log error without heavy logging framework
        print(f"Hook upload failed: {e}", file=sys.stderr)
        return False


def record_commit_fast(commit_sha: Optional[str] = None) -> None:
    """Ultra-fast commit recording with minimal overhead."""
    start_time = time.time()

    try:
        # Get commit SHA efficiently
        if not commit_sha:
            commit_sha = _git_command_fast(["rev-parse", "HEAD"])

        if not commit_sha:
            return  # Not a git repo

        # Create payload with batched operations
        payload = _create_commit_payload(commit_sha)

        # Submit to vector store
        _submit_to_vector_store_fast(payload, commit_sha)

        # Optional: Log performance for monitoring
        elapsed = (time.time() - start_time) * 1000
        if elapsed > 500:  # Only log slow executions
            print(f"Hook took {elapsed:.1f}ms for {commit_sha[:8]}", file=sys.stderr)

    except Exception as e:
        # Minimal error handling to prevent git operation blocking
        elapsed = (time.time() - start_time) * 1000
        print(f"Hook error after {elapsed:.1f}ms: {e}", file=sys.stderr)


if __name__ == "__main__":
    # Add startup optimizations
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")  # Skip .pyc creation
    os.environ.setdefault("PYTHONOPTIMIZE", "1")  # Enable optimizations

    record_commit_fast()
