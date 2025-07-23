"""Storage of git commits in vector store."""

import json
import logging
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from ..utils.vector_store import get_client
from ..utils.redaction import redact_dict, redact_secrets
from .config import get_memory_config

logger = logging.getLogger(__name__)


def store_commit_memory(commit_sha: Optional[str] = None) -> None:
    """Store commit information in vector store.

    Args:
        commit_sha: Specific commit SHA to store. If None, uses HEAD.
    """
    try:
        # Get commit information
        if not commit_sha:
            commit_sha = _git_command(["rev-parse", "HEAD"])

        if not commit_sha:
            logger.info("No git repository found")
            return

        # Get commit details
        parent_sha = _git_command(["rev-parse", f"{commit_sha}~1"]) or "root"
        branch = _git_command(["branch", "--show-current"]) or "main"

        # Get commit message
        commit_message = _git_command(["log", "-1", "--pretty=%B", commit_sha]) or ""

        # Get changed files
        files_output = (
            _git_command(
                ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha]
            )
            or ""
        )
        changed_files = [f for f in files_output.split("\n") if f]

        # Get commit timestamp
        timestamp_str = _git_command(["show", "-s", "--format=%ct", commit_sha])
        timestamp = int(timestamp_str) if timestamp_str else int(time.time())

        # Check if this is a merge commit
        parent_count_str = _git_command(
            ["rev-list", "--parents", "-n", "1", commit_sha]
        )
        is_merge_commit = (
            len(parent_count_str.split()) > 2 if parent_count_str else False
        )

        # Count commits since main/master
        commits_since_main = 0
        if branch != "main" and branch != "master":
            count_str = _git_command(["rev-list", "--count", "origin/main..HEAD"])
            if count_str and count_str.isdigit():
                commits_since_main = int(count_str)

        # Try to find associated session_id from recent session cache
        from ..config import get_settings

        settings = get_settings()
        session_id = find_recent_session_id()

        # Create summary
        summary = create_commit_summary(commit_sha, commit_message, changed_files)

        # Create document with metadata
        doc = {
            "content": summary,
            "commit_message": redact_secrets(commit_message),  # Redact message
            "metadata": {
                "type": "commit",
                "commit_sha": commit_sha,
                "parent_sha": parent_sha,
                "branch": branch,
                "is_merge_commit": is_merge_commit,
                "commits_since_main": commits_since_main,
                "timestamp": timestamp,
                "datetime": datetime.fromtimestamp(timestamp).isoformat(),
                "files_changed": changed_files[: settings.memory_max_files_per_commit],
                "session_id": session_id,  # May be None
            },
        }

        # Redact any secrets from the document
        doc = redact_dict(doc)

        # Get active store and upload
        config = get_memory_config()
        store_id = config.get_active_commit_store()

        # Create temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f"_commit_{commit_sha[:8]}.json", delete=False
        ) as tmp_file:
            json.dump(doc, tmp_file, indent=2)
            tmp_path = tmp_file.name

        try:
            # Upload to vector store (fire-and-forget to prevent hangs)
            client = get_client()
            with open(tmp_path, "rb") as f:
                # First upload file to OpenAI
                file_obj = client.files.create(file=f, purpose="assistants")
                # Then add to vector store
                client.vector_stores.files.create(
                    vector_store_id=store_id, file_id=file_obj.id
                )

            # Increment count
            config.increment_commit_count()

            logger.info(f"Stored commit {commit_sha[:8]} in project history")

        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)

    except Exception:
        logger.exception("Failed to store commit memory")


def find_recent_session_id() -> Optional[str]:
    """Try to find a recent session_id from the session cache.

    This is a best-effort attempt to correlate commits with conversations.
    """
    try:
        # Check for session cache database
        from ..config import get_settings

        settings = get_settings()
        db_path = settings.session_db_path
        if not Path(db_path).exists():
            return None

        # Look for sessions updated in the last 2 hours
        cutoff_hours = settings.memory_session_cutoff_hours
        cutoff = int(time.time()) - (cutoff_hours * 3600)

        with sqlite3.connect(db_path) as db:
            cur = db.execute(
                "SELECT session_id FROM sessions WHERE updated_at > ? ORDER BY updated_at DESC LIMIT 1",
                (cutoff,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    except Exception:
        # If anything fails, just return None
        return None


def create_commit_summary(commit_sha: str, message: str, files: List[str]) -> str:
    """Create a summary of the commit.

    In production, this would use Gemini Flash for summarization.
    For now, we create a structured summary.
    """
    # Get diff statistics
    diff_stats = (
        _git_command(["show", "--stat", commit_sha]) or "No statistics available"
    )

    # Extract key parts
    lines = diff_stats.split("\n")
    stats_line = lines[-1] if lines else "No statistics available"

    summary = f"""## Git Commit: {commit_sha[:8]}

**Date**: {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}

### Commit Message
{message}

### Changes Summary
{stats_line}

### Files Modified ({len(files)} files)
{chr(10).join(f"- {f}" for f in files[:10])}
{f"... and {len(files) - 10} more files" if len(files) > 10 else ""}

### Context
This commit may be related to recent AI consultations.
Check conversations with matching session_id or timestamp for design rationale.
"""

    return summary


def _git_command(args: List[str]) -> Optional[str]:
    """Execute git command safely and return output."""
    try:
        result = subprocess.run(
            ["git"] + args, capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.debug(f"Git command failed: {' '.join(args)} - {result.stderr}")
            return None
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.debug(f"Git command error: {e}")
        return None


def main():
    """Entry point for git hook."""
    store_commit_memory()


if __name__ == "__main__":
    main()
