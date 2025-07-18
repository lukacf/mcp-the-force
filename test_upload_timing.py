#!/usr/bin/env python3
"""Test to measure vector store batch upload timing with parallel batches"""

import asyncio
import time
import glob
import os
from openai import AsyncOpenAI
from typing import List, BinaryIO


async def upload_batch(
    client: AsyncOpenAI, vector_store_id: str, files: List[BinaryIO], batch_num: int
) -> dict:
    """Upload a single batch of files and return timing info"""
    start = time.time()
    try:
        print(f"  Batch {batch_num}: Starting upload of {len(files)} files...")
        batch = await client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id, files=files
        )
        elapsed = time.time() - start
        print(
            f"  Batch {batch_num}: Completed in {elapsed:.2f}s - {batch.file_counts.completed}/{batch.file_counts.total} succeeded"
        )
        return {
            "batch_num": batch_num,
            "elapsed": elapsed,
            "completed": batch.file_counts.completed,
            "failed": batch.file_counts.failed,
            "total": batch.file_counts.total,
        }
    except Exception as e:
        elapsed = time.time() - start
        print(f"  Batch {batch_num}: Failed after {elapsed:.2f}s - {e}")
        return {
            "batch_num": batch_num,
            "elapsed": elapsed,
            "completed": 0,
            "failed": len(files),
            "total": len(files),
            "error": str(e),
        }


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
            size = os.path.getsize(path)
            # Skip empty or large files
            if size == 0 or size > 500_000:
                continue
            file_streams.append(open(path, "rb"))
        except Exception:
            pass

    print("\n=== SINGLE BATCH TEST ===")
    print(f"Uploading {len(file_streams)} files in one batch...")

    # Time the single batch upload
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

    # Now test with parallel batches
    print("\n=== PARALLEL BATCH TEST (10 batches) ===")

    # Create new vector store
    vs2 = await client.vector_stores.create(name="timing-test-parallel")

    # Reopen file streams
    file_streams = []
    for path in all_files:
        try:
            size = os.path.getsize(path)
            if size == 0 or size > 500_000:
                continue
            file_streams.append(open(path, "rb"))
        except Exception:
            pass

    print(f"Uploading {len(file_streams)} files in 10 parallel batches...")

    # Split files into 10 batches
    batch_size = max(1, len(file_streams) // 10)
    batches = []
    for i in range(0, len(file_streams), batch_size):
        batches.append(file_streams[i : i + batch_size])

    # Ensure we have exactly 10 batches (last one might be larger)
    while len(batches) > 10:
        batches[-2].extend(batches[-1])
        batches.pop()

    print(f"Created {len(batches)} batches with sizes: {[len(b) for b in batches]}")

    # Upload all batches in parallel
    start = time.time()
    try:
        tasks = [
            upload_batch(client, vs2.id, batch, i + 1)
            for i, batch in enumerate(batches)
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        # Calculate totals
        total_completed = sum(r["completed"] for r in results)
        total_failed = sum(r["failed"] for r in results)
        total_files = sum(r["total"] for r in results)

        print(f"\n✅ All batches completed in {elapsed:.2f}s")
        print(
            f"Total files: completed={total_completed}, failed={total_failed}, total={total_files}"
        )

        # Show individual batch times
        print("\nBatch timing details:")
        for r in sorted(results, key=lambda x: x["batch_num"]):
            print(
                f"  Batch {r['batch_num']}: {r['elapsed']:.2f}s ({r['completed']}/{r['total']} files)"
            )

        print(f"\n🚀 SPEEDUP: {elapsed:.2f}s parallel vs single batch")

    finally:
        # Cleanup
        for f in file_streams:
            try:
                f.close()
            except Exception:
                pass
        await client.vector_stores.delete(vs2.id)


if __name__ == "__main__":
    asyncio.run(time_batch_upload())
