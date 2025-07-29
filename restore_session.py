#!/usr/bin/env python3
"""Restore session-management-simplified from backup."""

import asyncio
import sqlite3
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_the_force.unified_session_cache import UnifiedSessionCache, _get_instance


async def restore_session():
    """Restore the session from backup."""

    # Connect to backup database
    backup_db = sqlite3.connect(
        "/Users/luka/.mcp_backups/.mcp_sessions_20250729_003602.sqlite3"
    )
    backup_db.row_factory = sqlite3.Row

    # Get the session from backup
    cursor = backup_db.cursor()
    cursor.execute("""
        SELECT project, tool, session_id, history, provider_metadata, updated_at 
        FROM unified_sessions 
        WHERE session_id = 'session-management-simplified'
    """)

    row = cursor.fetchone()
    if not row:
        print("Session not found in backup!")
        return

    print("Found session in backup:")
    print(f"  Project: {row['project']}")
    print(f"  Tool: {row['tool']}")
    print(f"  Session ID: {row['session_id']}")
    print(f"  History size: {len(row['history'])} bytes")

    # Delete existing session if it exists
    cache = _get_instance()
    await cache._execute_async(
        "DELETE FROM unified_sessions WHERE session_id = ?",
        ("session-management-simplified",),
    )
    print("\nDeleted existing session (if any)")

    # Insert the restored session
    await cache._execute_async(
        """INSERT INTO unified_sessions 
           (project, tool, session_id, history, provider_metadata, updated_at) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            row["project"],
            row["tool"],
            row["session_id"],
            row["history"],
            row["provider_metadata"],
            row["updated_at"],
        ),
    )
    print("Restored session from backup")

    # Verify restoration
    restored = await UnifiedSessionCache.get_session(
        row["project"], row["tool"], row["session_id"]
    )
    if restored:
        print(f"\nVerification: Session restored with {len(restored.history)} messages")
    else:
        print("\nERROR: Failed to verify restoration")

    backup_db.close()


if __name__ == "__main__":
    asyncio.run(restore_session())
