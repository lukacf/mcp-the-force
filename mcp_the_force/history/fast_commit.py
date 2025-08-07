"""Fast commit recording with lazy imports and minimal dependencies."""

import os
import sys
import time
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING

# Type hints only loaded during type checking
if TYPE_CHECKING:
    from ..vectorstores.manager import VectorStoreManager
    from ..config import Settings

# Global caches for expensive operations
_settings_cache: Optional["Settings"] = None
_vector_manager_cache: Optional["VectorStoreManager"] = None
_http_session_cache = None


class LazyImporter:
    """Lazy import manager for expensive dependencies."""

    def __init__(self):
        self._imports = {}
        self._import_times = {}

    def get(self, module_path: str, attr: Optional[str] = None):
        """Get module or attribute with lazy loading and timing."""
        cache_key = f"{module_path}.{attr}" if attr else module_path

        if cache_key not in self._imports:
            start_time = time.time()

            try:
                module = __import__(module_path, fromlist=[attr] if attr else [])
                self._imports[cache_key] = getattr(module, attr) if attr else module
                self._import_times[cache_key] = (time.time() - start_time) * 1000
            except ImportError as e:
                self._imports[cache_key] = None
                self._import_times[cache_key] = (time.time() - start_time) * 1000
                print(f"Import failed for {cache_key}: {e}", file=sys.stderr)

        return self._imports[cache_key]

    def get_import_stats(self) -> Dict[str, float]:
        """Get import timing statistics."""
        return self._import_times.copy()


# Global lazy importer
_lazy = LazyImporter()


def _get_settings_fast() -> "Settings":
    """Get settings with caching and lazy loading."""
    global _settings_cache

    if _settings_cache is None:
        # Try to use minimal config first
        try:
            get_settings = _lazy.get("mcp_the_force.config", "get_settings")
            if get_settings:
                _settings_cache = get_settings()
            else:
                # Fallback to minimal settings
                _settings_cache = _create_minimal_settings()
        except Exception:
            _settings_cache = _create_minimal_settings()

    return _settings_cache


def _create_minimal_settings():
    """Create minimal settings object without full config system."""
    from types import SimpleNamespace

    return SimpleNamespace(
        history_max_files_per_commit=50,
        session_db_path=".mcp-the-force/sessions.sqlite3",
        history_session_cutoff_hours=2,
    )


def _get_vector_manager() -> Optional["VectorStoreManager"]:
    """Get vector store manager with lazy loading."""
    global _vector_manager_cache

    if _vector_manager_cache is None:
        manager = _lazy.get(
            "mcp_the_force.vectorstores.manager", "vector_store_manager"
        )
        _vector_manager_cache = manager

    return _vector_manager_cache


def _git_command_optimized(args: List[str]) -> Optional[str]:
    """Execute git command with optimizations."""
    try:
        # Use more efficient subprocess call
        result = subprocess.run(
            ["git"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # Suppress errors for performance
            text=True,
            check=False,
            timeout=3,  # Aggressive timeout
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None


def _batch_git_commands(commit_sha: str) -> Dict[str, Optional[str]]:
    """Execute multiple git commands in batch for efficiency."""
    commands = {
        "parent": ["rev-parse", f"{commit_sha}~1"],
        "branch": ["branch", "--show-current"],
        "message": ["log", "-1", "--pretty=%B", commit_sha],
        "files": ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha],
        "timestamp": ["show", "-s", "--format=%ct", commit_sha],
    }

    results = {}
    for key, args in commands.items():
        results[key] = _git_command_optimized(args)

    return results


def _find_session_id_fast() -> Optional[str]:
    """Fast session lookup with minimal SQLite overhead."""
    try:
        settings = _get_settings_fast()
        db_path = Path(settings.session_db_path)

        if not db_path.exists():
            return None

        # Import sqlite3 only when needed
        sqlite3 = _lazy.get("sqlite3")
        if not sqlite3:
            return None

        cutoff = int(time.time()) - (settings.history_session_cutoff_hours * 3600)

        # Use optimized SQLite connection
        with sqlite3.connect(str(db_path), timeout=0.5) as db:
            # Enable optimizations
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.execute("PRAGMA cache_size=-2000")  # 2MB cache

            cur = db.execute(
                "SELECT session_id FROM unified_sessions WHERE updated_at > ? ORDER BY updated_at DESC LIMIT 1",
                (cutoff,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _create_commit_document(
    commit_sha: str, git_data: Dict[str, Optional[str]]
) -> Dict[str, Any]:
    """Create commit document with minimal processing."""
    settings = _get_settings_fast()

    # Process git data
    parent_sha = git_data.get("parent") or "root"
    branch = git_data.get("branch") or "main"
    commit_message = git_data.get("message") or ""
    files_output = git_data.get("files") or ""
    timestamp_str = git_data.get("timestamp")

    # Parse changed files
    changed_files = [f.strip() for f in files_output.split("\n") if f.strip()]
    timestamp = (
        int(timestamp_str)
        if timestamp_str and timestamp_str.isdigit()
        else int(time.time())
    )

    # Get session ID
    session_id = _find_session_id_fast()

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


def _upload_to_vector_store_fast(document: Dict[str, Any], commit_sha: str) -> bool:
    """Upload to vector store with minimal async overhead."""
    try:
        # Create temp file efficiently
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f"_commit_{commit_sha[:8]}.json", delete=False
        ) as tmp_file:
            json.dump(document, tmp_file, separators=(",", ":"))
            tmp_path = tmp_file.name

        try:
            # Import heavy dependencies only when uploading
            asyncio = _lazy.get("asyncio")
            if not asyncio:
                return False

            # Get vector store components
            vector_manager = _get_vector_manager()
            if not vector_manager:
                return False

            VSFile = _lazy.get("mcp_the_force.vectorstores.protocol", "VSFile")
            get_history_config = _lazy.get(
                "mcp_the_force.history.config", "get_history_config"
            )

            if not VSFile or not get_history_config:
                return False

            # Perform upload
            async def upload():
                with open(tmp_path, "r") as f:
                    content = f.read()

                vs_file = VSFile(
                    path=f"commits/{commit_sha}.json",
                    content=content,
                    metadata={"type": "commit", "sha": commit_sha},
                )

                config = get_history_config()
                store_id = config.get_active_commit_store()

                client = vector_manager._get_client(vector_manager.provider)
                store = await client.get(store_id)
                await store.add_files([vs_file])

                config.increment_commit_count()
                return True

            # Run with minimal event loop
            try:
                loop = asyncio.get_running_loop()
                # If we're already in a loop, skip upload to avoid blocking
                return False
            except RuntimeError:
                # Create new event loop
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    return loop.run_until_complete(upload())
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except Exception as e:
        print(f"Vector store upload failed: {e}", file=sys.stderr)
        return False


def record_commit_fast(commit_sha: Optional[str] = None) -> None:
    """Record commit with maximum performance optimizations."""
    start_time = time.time()

    try:
        # Get commit SHA
        if not commit_sha:
            commit_sha = _git_command_optimized(["rev-parse", "HEAD"])

        if not commit_sha:
            return  # Not in a git repository

        # Batch git operations
        git_data = _batch_git_commands(commit_sha)

        # Create document
        document = _create_commit_document(commit_sha, git_data)

        # Upload to vector store
        _upload_to_vector_store_fast(document, commit_sha)

        # Performance monitoring
        elapsed = (time.time() - start_time) * 1000
        if elapsed > 200:  # Log slow operations
            import_stats = _lazy.get_import_stats()
            total_import_time = sum(import_stats.values())
            print(
                f"Hook: {elapsed:.1f}ms total, {total_import_time:.1f}ms imports",
                file=sys.stderr,
            )

    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"Hook failed after {elapsed:.1f}ms: {e}", file=sys.stderr)


def main():
    """Entry point optimized for git hook usage."""
    # Set performance environment variables
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    os.environ.setdefault("PYTHONOPTIMIZE", "1")
    os.environ.setdefault("PYTHONHASHSEED", "0")  # Deterministic hashing

    record_commit_fast()


if __name__ == "__main__":
    main()
