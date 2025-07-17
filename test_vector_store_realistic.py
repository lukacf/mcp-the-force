#!/usr/bin/env python3
"""Test vector store with realistic codebase files"""

import asyncio
import time
from pathlib import Path
from openai import AsyncOpenAI
import glob

async def test_with_codebase_files():
    """Test with actual codebase files like in the real scenario"""
    print("=== Testing Vector Store with Codebase Files ===")
    
    client = AsyncOpenAI()
    
    # Get Python files from the project
    print("\n1. Gathering codebase files...")
    py_files = glob.glob("/Users/luka/src/cc/mcp-second-brain/**/*.py", recursive=True)
    md_files = glob.glob("/Users/luka/src/cc/mcp-second-brain/**/*.md", recursive=True)
    
    # Take first 96 files to match the scenario
    all_files = (py_files + md_files)[:96]
    print(f"   Found {len(all_files)} files")
    
    # Calculate total size
    total_size = sum(Path(f).stat().st_size for f in all_files)
    print(f"   Total size: {total_size / 1024 / 1024:.2f} MB")
    
    try:
        # Create vector store
        print("\n2. Creating vector store...")
        start = time.time()
        vs = await client.vector_stores.create(name="test-codebase-store")
        print(f"   Created: {vs.id} in {time.time()-start:.2f}s")
        
        # Open all files
        print("\n3. Opening file streams...")
        file_streams = []
        failed_files = []
        
        for file_path in all_files:
            try:
                # Verify file exists and is readable
                path = Path(file_path)
                if not path.exists():
                    failed_files.append(file_path)
                    continue
                    
                # Check file size
                size = path.stat().st_size
                if size == 0:
                    print(f"   Skipping empty file: {file_path}")
                    continue
                if size > 500_000:  # 500KB limit
                    print(f"   Skipping large file: {file_path} ({size} bytes)")
                    continue
                    
                # Try to read file first to verify encoding
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        f.read(100)  # Read first 100 chars
                except:
                    print(f"   Skipping file with encoding issues: {file_path}")
                    continue
                
                # Now open for upload
                stream = open(file_path, "rb")
                file_streams.append(stream)
                
            except Exception as e:
                print(f"   Error opening {file_path}: {e}")
                failed_files.append(file_path)
        
        print(f"   Opened {len(file_streams)} files successfully")
        if failed_files:
            print(f"   Failed to open {len(failed_files)} files")
        
        # Start batch upload
        print(f"\n4. Starting batch upload of {len(file_streams)} files...")
        print("   This is where it might hang in the real scenario...")
        
        start_time = time.time()
        
        # Create upload task with timeout
        upload_task = asyncio.create_task(
            client.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vs.id,
                files=file_streams
            )
        )
        
        # Monitor progress
        print("   Waiting for upload (timeout: 60s)...")
        try:
            batch = await asyncio.wait_for(upload_task, timeout=60.0)
            elapsed = time.time() - start_time
            
            print(f"\n   ✓ Upload completed in {elapsed:.2f}s!")
            print(f"   Status: {batch.status}")
            print(f"   Completed: {batch.file_counts.completed}")
            print(f"   Failed: {batch.file_counts.failed}")
            print(f"   Total: {batch.file_counts.total}")
            
        except asyncio.TimeoutError:
            print(f"\n   ✗ Upload timed out after 60s!")
            print("   Attempting to cancel...")
            upload_task.cancel()
            try:
                await upload_task
            except asyncio.CancelledError:
                print("   Successfully cancelled upload task")
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        print("\n5. Cleaning up...")
        for stream in file_streams:
            try:
                stream.close()
            except:
                pass
        
        try:
            await client.vector_stores.delete(vs.id)
            print("   Deleted vector store")
        except:
            pass

async def test_with_polling_details():
    """Test with manual polling to see what's happening"""
    print("\n=== Testing with Manual Polling ===")
    
    client = AsyncOpenAI()
    
    # Just use 20 files for this test
    files = glob.glob("/Users/luka/src/cc/mcp-second-brain/**/*.py", recursive=True)[:20]
    
    vs = await client.vector_stores.create(name="test-polling")
    
    # Upload files first
    print("Uploading files individually first...")
    file_ids = []
    for i, path in enumerate(files):
        with open(path, "rb") as f:
            file_obj = await client.files.create(file=f, purpose="assistants")
            file_ids.append(file_obj.id)
        print(f"  Uploaded {i+1}/{len(files)}: {Path(path).name}")
    
    # Create batch without polling
    print("\nCreating file batch (without polling)...")
    batch = await client.vector_stores.file_batches.create(
        vector_store_id=vs.id,
        file_ids=file_ids
    )
    print(f"Batch created: {batch.id}, status: {batch.status}")
    
    # Manual polling
    print("\nManual polling...")
    start = time.time()
    while batch.status in ["in_progress", "pending"]:
        await asyncio.sleep(2)
        batch = await client.vector_stores.file_batches.retrieve(
            vector_store_id=vs.id,
            batch_id=batch.id
        )
        elapsed = time.time() - start
        print(f"  [{elapsed:.1f}s] Status: {batch.status}, "
              f"Completed: {batch.file_counts.completed}/{batch.file_counts.total}")
        
        if elapsed > 30:
            print("  Stopping after 30s...")
            break
    
    # Cleanup
    try:
        await client.vector_stores.delete(vs.id)
    except:
        pass

if __name__ == "__main__":
    asyncio.run(test_with_codebase_files())
    asyncio.run(test_with_polling_details())