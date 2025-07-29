#!/usr/bin/env python3
"""Debug script to find all sessions and their sizes."""

import asyncio
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_the_force.unified_session_cache import _get_instance


async def debug_all_sessions():
    """List all sessions in the database."""

    cache = _get_instance()

    # Query all sessions
    rows = await cache._execute_async(
        """SELECT project, tool, session_id, LENGTH(history) as history_size, updated_at 
           FROM unified_sessions 
           WHERE session_id LIKE '%session-management%'
           ORDER BY updated_at DESC""",
        (),
    )

    print(f"Found {len(rows)} session(s) with 'session-management' in the ID:")
    print("-" * 80)

    for row in rows:
        print(f"Project: {row[0]}")
        print(f"Tool: {row[1]}")
        print(f"Session ID: {row[2]}")
        print(f"History size: {row[3]:,} bytes")
        print(f"Updated at: {row[4]}")
        print("-" * 80)


if __name__ == "__main__":
    asyncio.run(debug_all_sessions())
