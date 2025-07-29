#!/usr/bin/env python3
"""Debug script to investigate session-management-simplified."""

import asyncio
import json
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_the_force.unified_session_cache import UnifiedSessionCache, _get_instance
from mcp_the_force.config import get_settings


async def debug_session():
    """Debug the session-management-simplified session."""

    settings = get_settings()
    project = Path(settings.logging.project_path or ".").name

    print(f"Project: {project}")
    print("-" * 50)

    # Try to find the session with different project/tool combinations
    cache = _get_instance()

    # Query the database directly to find all sessions with this ID
    rows = await cache._execute_async(
        "SELECT project, tool, session_id, LENGTH(history) as history_size, updated_at FROM unified_sessions WHERE session_id = ?",
        ("session-management-simplified",),
    )

    if not rows:
        print("No sessions found with session_id='session-management-simplified'")
        return

    print(f"Found {len(rows)} session(s) with this ID:")
    for row in rows:
        print(f"  Project: {row[0]}")
        print(f"  Tool: {row[1]}")
        print(f"  Session ID: {row[2]}")
        print(f"  History size: {row[3]} bytes")
        print(f"  Updated at: {row[4]}")
        print()

        # Try to get the actual session
        session = await UnifiedSessionCache.get_session(row[0], row[1], row[2])
        if session:
            print(f"  History length: {len(session.history)} messages")
            if session.history:
                # Show all messages briefly
                for i, msg in enumerate(session.history):
                    role = msg.get("role", "unknown")
                    content = (
                        str(msg.get("content", ""))[:100] + "..."
                        if len(str(msg.get("content", ""))) > 100
                        else str(msg.get("content", ""))
                    )
                    print(f"  Message {i+1}: {role} - {content}")
                # Count total characters in history
                total_chars = sum(len(json.dumps(msg)) for msg in session.history)
                print(f"  Total history characters: {total_chars}")
        else:
            print("  Could not retrieve session object")
        print("-" * 50)


if __name__ == "__main__":
    asyncio.run(debug_session())
