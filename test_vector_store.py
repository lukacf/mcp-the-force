#!/usr/bin/env python3
"""Test script to debug vector store hanging issue"""

import asyncio
import time
import signal
from pathlib import Path
from openai import AsyncOpenAI

# Global flag for cancellation
cancelled = False

def signal_handler(signum, frame):
    global cancelled
    cancelled = True
    print("\n[SIGNAL] Received SIGINT - setting cancelled flag")

async def test_vector_store_basic():
    """Test basic vector store operations"""
    print("=== Testing Vector Store Operations ===")
    
    client = AsyncOpenAI()
    
    try:
        # Step 1: Create vector store
        print("\n1. Creating vector store...")
        start = time.time()
        vs = await client.vector_stores.create(name="test-debug-store")
        print(f"   Created vector store: {vs.id} in {time.time()-start:.2f}s")
        
        # Step 2: Prepare test files
        print("\n2. Preparing test files...")
        test_files = []
        test_dir = Path("/tmp/vector_test")
        test_dir.mkdir(exist_ok=True)
        
        # Create 10 small test files
        for i in range(10):
            file_path = test_dir / f"test_{i}.txt"
            file_path.write_text(f"This is test file {i}\n" * 100)
            test_files.append(str(file_path))
            
        print(f"   Created {len(test_files)} test files")
        
        # Step 3: Upload files individually (non-batch)
        print("\n3. Testing individual file uploads...")
        file_ids = []
        for i, path in enumerate(test_files[:3]):  # Just first 3
            start = time.time()
            with open(path, "rb") as f:
                file_obj = await client.files.create(file=f, purpose="assistants")
                file_ids.append(file_obj.id)
            print(f"   Uploaded file {i}: {file_obj.id} in {time.time()-start:.2f}s")
        
        # Step 4: Add files to vector store one by one
        print("\n4. Adding files to vector store individually...")
        for i, file_id in enumerate(file_ids):
            start = time.time()
            await client.vector_stores.files.create(
                vector_store_id=vs.id,
                file_id=file_id
            )
            print(f"   Added file {i} to vector store in {time.time()-start:.2f}s")
        
        # Step 5: Test batch upload
        print("\n5. Testing batch upload with upload_and_poll...")
        print("   Opening file streams...")
        file_streams = []
        for path in test_files[3:]:  # Remaining files
            file_streams.append(open(path, "rb"))
        
        print(f"   Starting batch upload of {len(file_streams)} files...")
        print("   [Press Ctrl+C to test cancellation]")
        
        start = time.time()
        try:
            # This is where it might hang
            batch = await client.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vs.id,
                files=file_streams
            )
            elapsed = time.time() - start
            print(f"   Batch upload completed in {elapsed:.2f}s")
            print(f"   Status: {batch.status}")
            print(f"   Files: {batch.file_counts}")
        except asyncio.CancelledError:
            print("   [CANCELLED] Batch upload was cancelled!")
            raise
        except Exception as e:
            print(f"   [ERROR] Batch upload failed: {e}")
        finally:
            # Always close file streams
            for stream in file_streams:
                stream.close()
        
        # Step 6: Cleanup
        print("\n6. Cleaning up...")
        try:
            await client.vector_stores.delete(vs.id)
            print("   Deleted vector store")
        except:
            pass
            
        # Cleanup test files
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)
        
        print("\n=== Test Complete ===")
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

async def test_vector_store_cancellation():
    """Test cancellation of vector store operations"""
    print("\n=== Testing Vector Store Cancellation ===")
    
    client = AsyncOpenAI()
    
    # Create test files
    test_dir = Path("/tmp/vector_cancel_test")
    test_dir.mkdir(exist_ok=True)
    
    # Create 50 files to make it take longer
    print("Creating 50 test files...")
    file_streams = []
    for i in range(50):
        file_path = test_dir / f"large_test_{i}.txt"
        # Make them bigger to slow down upload
        file_path.write_text(f"This is a larger test file {i}\n" * 1000)
        file_streams.append(open(str(file_path), "rb"))
    
    print("Creating vector store...")
    vs = await client.vector_stores.create(name="test-cancel-store")
    
    print(f"Starting batch upload of 50 files (press Ctrl+C within 5 seconds)...")
    
    # Create a task for the upload
    upload_task = asyncio.create_task(
        client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vs.id,
            files=file_streams
        )
    )
    
    # Wait for 5 seconds or until cancelled
    try:
        await asyncio.wait_for(upload_task, timeout=5.0)
        print("Upload completed before timeout")
    except asyncio.TimeoutError:
        print("[TIMEOUT] Upload took longer than 5 seconds, cancelling...")
        upload_task.cancel()
        try:
            await upload_task
        except asyncio.CancelledError:
            print("[SUCCESS] Task was successfully cancelled!")
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
    
    # Cleanup
    for stream in file_streams:
        stream.close()
    
    try:
        await client.vector_stores.delete(vs.id)
    except:
        pass
        
    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)
    
    print("\n=== Cancellation Test Complete ===")

async def main():
    """Run all tests"""
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Test 1: Basic operations
    await test_vector_store_basic()
    
    # Test 2: Cancellation
    await test_vector_store_cancellation()

if __name__ == "__main__":
    asyncio.run(main())