#!/usr/bin/env python3
"""Get detailed information about vector store file failures"""

import asyncio
import time
from pathlib import Path
from openai import AsyncOpenAI
import glob

async def test_with_failure_details():
    """Test and get details about file failures"""
    print("=== Testing Vector Store with Failure Details ===")
    
    client = AsyncOpenAI()
    
    # Get files
    py_files = glob.glob("/Users/luka/src/cc/mcp-second-brain/**/*.py", recursive=True)
    md_files = glob.glob("/Users/luka/src/cc/mcp-second-brain/**/*.md", recursive=True)
    all_files = (py_files + md_files)[:96]
    
    print(f"\n1. Found {len(all_files)} files")
    
    # Create vector store
    vs = await client.vector_stores.create(name="test-failures")
    print(f"\n2. Created vector store: {vs.id}")
    
    # First, upload files individually to get file IDs
    print("\n3. Uploading files to get file IDs...")
    file_mappings = {}  # file_id -> file_path
    file_streams = []
    
    for i, file_path in enumerate(all_files):
        try:
            # Check file
            path = Path(file_path)
            if not path.exists() or path.stat().st_size == 0:
                continue
                
            # Try to read first
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.read(100)
            except:
                print(f"   Skipping {path.name} - encoding issues")
                continue
            
            # Open for batch upload
            stream = open(file_path, "rb")
            file_streams.append(stream)
            
            if i % 20 == 0:
                print(f"   Prepared {i}/{len(all_files)} files...")
                
        except Exception as e:
            print(f"   Error with {file_path}: {e}")
    
    print(f"\n4. Starting batch upload of {len(file_streams)} files...")
    
    try:
        # Do the batch upload
        start = time.time()
        batch = await client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vs.id,
            files=file_streams
        )
        elapsed = time.time() - start
        
        print(f"\n5. Upload completed in {elapsed:.2f}s")
        print(f"   Status: {batch.status}")
        print(f"   Completed: {batch.file_counts.completed}")
        print(f"   Failed: {batch.file_counts.failed}")
        print(f"   In Progress: {batch.file_counts.in_progress}")
        print(f"   Cancelled: {batch.file_counts.cancelled}")
        print(f"   Total: {batch.file_counts.total}")
        
        # Get the batch details to see failures
        print(f"\n6. Fetching batch files to see failures...")
        
        # List files in the batch
        batch_files = await client.vector_stores.file_batches.list_files(
            vector_store_id=vs.id,
            batch_id=batch.id,
            limit=100
        )
        
        failed_files = []
        succeeded_files = []
        
        for file in batch_files.data:
            if hasattr(file, 'status'):
                if file.status == 'failed':
                    failed_files.append(file)
                elif file.status == 'completed':
                    succeeded_files.append(file)
        
        print(f"\n7. File Details:")
        print(f"   Succeeded: {len(succeeded_files)}")
        print(f"   Failed: {len(failed_files)}")
        
        if failed_files:
            print("\n8. Failed File Details:")
            for i, file in enumerate(failed_files[:10]):  # Show first 10
                print(f"\n   Failed file {i+1}:")
                print(f"   - File ID: {file.id}")
                print(f"   - Status: {file.status}")
                if hasattr(file, 'last_error'):
                    print(f"   - Error: {file.last_error}")
                if hasattr(file, 'status_details'):
                    print(f"   - Details: {file.status_details}")
                    
                # Try to get more info about the file
                try:
                    file_info = await client.files.retrieve(file.id)
                    print(f"   - Filename: {file_info.filename}")
                    print(f"   - Size: {file_info.bytes} bytes")
                except:
                    pass
        
    except Exception as e:
        print(f"\n[ERROR] Batch upload failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        for stream in file_streams:
            try:
                stream.close()
            except:
                pass
                
        try:
            await client.vector_stores.delete(vs.id)
        except:
            pass

async def test_individual_file_issues():
    """Upload files individually to identify problematic ones"""
    print("\n=== Testing Individual File Uploads ===")
    
    client = AsyncOpenAI()
    
    # Test specific file types
    test_patterns = [
        "/Users/luka/src/cc/mcp-second-brain/**/*.egg-info/**/*",
        "/Users/luka/src/cc/mcp-second-brain/**/__pycache__/**/*",
        "/Users/luka/src/cc/mcp-second-brain/**/test_*.py",
    ]
    
    for pattern in test_patterns:
        files = glob.glob(pattern, recursive=True)[:5]
        if files:
            print(f"\nTesting pattern: {pattern}")
            for file_path in files:
                try:
                    path = Path(file_path)
                    size = path.stat().st_size
                    
                    with open(file_path, "rb") as f:
                        file_obj = await client.files.create(file=f, purpose="assistants")
                        print(f"  ✓ {path.name} ({size} bytes) -> {file_obj.id}")
                except Exception as e:
                    print(f"  ✗ {path.name}: {str(e)[:100]}")

if __name__ == "__main__":
    asyncio.run(test_with_failure_details())
    asyncio.run(test_individual_file_issues())