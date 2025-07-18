#!/usr/bin/env python3
"""Simple test to measure vector store batch upload timing"""

import asyncio
import time
import glob
from openai import AsyncOpenAI


async def time_batch_upload():
    """Time a simple batch upload of project files"""
    client = AsyncOpenAI()

    # Get ~90 files like in the MCP scenario
    py_files = glob.glob("/Users/luka/src/cc/mcp-second-brain/**/*.py", recursive=True)
    md_files = glob.glob("/Users/luka/src/cc/mcp-second-brain/**/*.md", recursive=True)
    all_files = (py_files + md_files)[:90]

    print(f"Testing batch upload of {len(all_files)} files...")

    # Create vector store
    vs = await client.vector_stores.create(name="timing-test")

    # Open file streams
    file_streams = []
    for path in all_files:
        try:
            import os

            size = os.path.getsize(path)
            # Skip empty or large files
            if size == 0 or size > 500_000:
                continue
            file_streams.append(open(path, "rb"))
        except Exception:
            pass

    print(f"Uploading {len(file_streams)} files...")

    # Time the upload
    start = time.time()
    try:
        batch = await client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vs.id, files=file_streams
        )
        elapsed = time.time() - start

        print(f"\nCompleted in {elapsed:.2f}s")
        print(f"Status: {batch.status}")
        print(
            f"File counts: completed={batch.file_counts.completed}, "
            f"failed={batch.file_counts.failed}, total={batch.file_counts.total}"
        )

        if elapsed > 30:
            print(f"\n⚠️  SLOW UPLOAD: {elapsed:.2f}s (expected ~15s)")
        else:
            print("\n✓ Normal speed")

    finally:
        # Cleanup
        for f in file_streams:
            f.close()
        await client.vector_stores.delete(vs.id)


if __name__ == "__main__":
    asyncio.run(time_batch_upload())
