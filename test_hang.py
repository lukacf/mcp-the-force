#!/usr/bin/env python3
"""Test script to isolate the hanging issue on second query."""

import asyncio
import logging
import sys

# Set up simple stderr logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)


async def test_openai_session_cache():
    """Test if the session cache SQLite operations are causing the hang."""
    from mcp_second_brain.session_cache import SessionCache

    cache = SessionCache()
    session_id = "test-session-001"

    print("Test 1: Setting response ID...", file=sys.stderr)
    await cache.set_response_id(session_id, "resp_001")
    print("✓ Set response ID completed", file=sys.stderr)

    print("\nTest 2: Getting response ID...", file=sys.stderr)
    result = await cache.get_response_id(session_id)
    print(f"✓ Got response ID: {result}", file=sys.stderr)

    print(
        "\nTest 3: Setting response ID again (simulating second query)...",
        file=sys.stderr,
    )
    await cache.set_response_id(session_id, "resp_002")
    print("✓ Second set completed", file=sys.stderr)

    print("\nTest 4: Getting response ID again...", file=sys.stderr)
    result = await cache.get_response_id(session_id)
    print(f"✓ Got response ID: {result}", file=sys.stderr)

    print("\nAll tests passed!", file=sys.stderr)


async def test_loiter_killer_client():
    """Test if the loiter killer client is causing the hang."""
    from mcp_second_brain.utils.loiter_killer_client import LoiterKillerClient

    client = LoiterKillerClient()
    session_id = "test-session-002"

    print("Test 1: Getting vector store...", file=sys.stderr)
    vs_id, files = await client.get_or_create_vector_store(session_id)
    print(f"✓ Got vector store: {vs_id}, files: {len(files)}", file=sys.stderr)

    if vs_id:
        print("\nTest 2: Releasing vector store...", file=sys.stderr)
        await client.release_vector_store(session_id, vs_id)
        print("✓ Released vector store", file=sys.stderr)

    print(
        "\nTest 3: Getting vector store again (simulating second query)...",
        file=sys.stderr,
    )
    vs_id, files = await client.get_or_create_vector_store(session_id)
    print(f"✓ Got vector store again: {vs_id}, files: {len(files)}", file=sys.stderr)

    print("\nAll tests passed!", file=sys.stderr)


async def main():
    print("=" * 60, file=sys.stderr)
    print("Testing components that might cause hang on second query", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    print("\n### Testing Session Cache ###", file=sys.stderr)
    await test_openai_session_cache()

    print("\n### Testing Loiter Killer Client ###", file=sys.stderr)
    await test_loiter_killer_client()

    print("\n" + "=" * 60, file=sys.stderr)
    print("All component tests completed successfully!", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
