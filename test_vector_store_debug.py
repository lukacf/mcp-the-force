#!/usr/bin/env python3
"""Debug why vector store hangs in MCP but not in isolation"""

import asyncio
import time
from pathlib import Path
from openai import AsyncOpenAI
import os

# List of files from the actual error log
PROBLEM_FILES = [
    "/Users/luka/src/cc/mcp-second-brain/mcp_second_brain/utils/file_tree.py",
    "/Users/luka/src/cc/mcp-second-brain/tests/unit/test_descriptors.py",
    "/Users/luka/src/cc/mcp-second-brain/tests/unit/test_openai_adapter/test_models.py",
    "/Users/luka/src/cc/mcp-second-brain/tests/unit/test_context_loader.py",
    "/Users/luka/src/cc/mcp-second-brain/tests/unit/test_structured_output_routing.py",
    "/Users/luka/src/cc/mcp-second-brain/mcp_second_brain/operation_manager.py",
    "/Users/luka/src/cc/mcp-second-brain/mcp_second_brain/prompts.py",
    "/Users/luka/src/cc/mcp-second-brain/mcp_second_brain/session_cache.py",
    "/Users/luka/src/cc/mcp-second-brain/tests/unit/test_openai_adapter/test_client.py",
    "/Users/luka/src/cc/mcp-second-brain/tests/integration_mcp/test_file_tree_integration.py",
]


async def test_specific_files():
    """Test with the exact files that were being uploaded when it hung"""
    print("=== Testing with Specific Problem Files ===")

    client = AsyncOpenAI()

    # Check if files exist and their sizes
    print("\n1. Checking files...")
    existing_files = []
    for file_path in PROBLEM_FILES[:10]:  # First 10 files
        if Path(file_path).exists():
            size = Path(file_path).stat().st_size
            print(f"   ✓ {Path(file_path).name}: {size:,} bytes")
            existing_files.append(file_path)
        else:
            print(f"   ✗ {Path(file_path).name}: NOT FOUND")

    # Test synchronous vs async client
    print("\n2. Testing AsyncOpenAI client initialization...")
    start = time.time()
    client = AsyncOpenAI()
    print(f"   Client created in {time.time()-start:.2f}s")

    # Test vector store creation
    print("\n3. Creating vector store...")
    start = time.time()
    vs = await client.vector_stores.create(name="debug-specific-files")
    print(f"   Created {vs.id} in {time.time()-start:.2f}s")

    # Test file upload one by one
    print("\n4. Uploading files individually...")
    file_ids = []
    for file_path in existing_files[:5]:
        start = time.time()
        try:
            with open(file_path, "rb") as f:
                file_obj = await client.files.create(file=f, purpose="assistants")
                file_ids.append(file_obj.id)
                print(
                    f"   ✓ {Path(file_path).name}: {file_obj.id} in {time.time()-start:.2f}s"
                )
        except Exception as e:
            print(f"   ✗ {Path(file_path).name}: {e}")

    # Test batch creation
    print("\n5. Testing batch creation...")
    if file_ids:
        start = time.time()
        batch = await client.vector_stores.file_batches.create(
            vector_store_id=vs.id, file_ids=file_ids
        )
        print(f"   Batch created: {batch.id} in {time.time()-start:.2f}s")

        # Poll manually
        print("\n6. Polling batch status...")
        for i in range(10):
            await asyncio.sleep(1)
            batch = await client.vector_stores.file_batches.retrieve(
                vector_store_id=vs.id, batch_id=batch.id
            )
            print(
                f"   [{i+1}s] Status: {batch.status}, Completed: {batch.file_counts.completed}/{batch.file_counts.total}"
            )
            if batch.status == "completed":
                break

    # Cleanup
    try:
        await client.vector_stores.delete(vs.id)
        print("\n7. Cleaned up vector store")
    except:
        pass


async def test_with_timeout_wrapper():
    """Test if the issue is related to how we wrap the operation"""
    print("\n=== Testing with Timeout Wrapper (like in real code) ===")

    client = AsyncOpenAI()

    # Create vector store
    vs = await client.vector_stores.create(name="timeout-test")

    # Prepare 20 test files
    test_files = []
    for i in range(20):
        path = f"/tmp/timeout_test_{i}.txt"
        with open(path, "w") as f:
            f.write(f"Test file {i}\n" * 1000)
        test_files.append(open(path, "rb"))

    print(f"Testing upload_and_poll with {len(test_files)} files...")

    # Simulate the operation_manager wrapper
    async def wrapped_upload():
        try:
            print("  Starting wrapped upload...")
            result = await client.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vs.id, files=test_files
            )
            print(f"  Upload completed: {result.status}")
            return result
        except asyncio.CancelledError:
            print("  [CANCELLED] in wrapped_upload")
            raise
        except Exception as e:
            print(f"  [ERROR] in wrapped_upload: {e}")
            raise
        finally:
            print("  Cleaning up file streams...")
            for f in test_files:
                f.close()

    # Test with asyncio.create_task (like operation_manager might do)
    start = time.time()
    task = asyncio.create_task(wrapped_upload())

    try:
        # Wait with timeout
        result = await asyncio.wait_for(task, timeout=30)
        print(f"Success! Completed in {time.time()-start:.2f}s")
    except asyncio.TimeoutError:
        print("Timeout after 30s! Cancelling...")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            print("Successfully cancelled")

    # Cleanup
    try:
        await client.vector_stores.delete(vs.id)
    except:
        pass

    # Clean temp files
    for i in range(20):
        try:
            os.unlink(f"/tmp/timeout_test_{i}.txt")
        except:
            pass


if __name__ == "__main__":
    # Test 1: Specific files
    asyncio.run(test_specific_files())

    # Test 2: With timeout wrapper
    asyncio.run(test_with_timeout_wrapper())
