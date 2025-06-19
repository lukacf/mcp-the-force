#!/usr/bin/env python3
"""
Debug script to test context processing directly without MCP overhead.
"""

import sys
import time
from pathlib import Path

# Add the project to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_second_brain.utils.prompt_builder import build_prompt
from mcp_second_brain.utils.fs import gather_file_paths

def test_file_gathering():
    """Test the file gathering step."""
    print("=== Testing file gathering ===")
    
    # Test single file (known to work)
    print("\n1. Testing single file (README.md):")
    start = time.time()
    files = gather_file_paths(["/Users/luka/src/cc/mcp-second-brain/README.md"])
    print(f"   Gathered {len(files)} files in {time.time() - start:.3f}s")
    print(f"   Files: {files}")
    
    # Test single small file  
    print("\n2. Testing single small file (pyproject.toml):")
    start = time.time()
    files = gather_file_paths(["/Users/luka/src/cc/mcp-second-brain/pyproject.toml"])
    print(f"   Gathered {len(files)} files in {time.time() - start:.3f}s")
    print(f"   Files: {files}")
    
    # Test directory
    print("\n3. Testing full directory:")
    start = time.time()
    files = gather_file_paths(["/Users/luka/src/cc/mcp-second-brain"])
    print(f"   Gathered {len(files)} files in {time.time() - start:.3f}s")
    print(f"   First 5 files: {files[:5]}")
    
    return files

def test_prompt_building(files):
    """Test the prompt building step."""
    print("\n=== Testing prompt building ===")
    
    # Test with single file
    print("\n1. Testing prompt building with README.md:")
    start = time.time()
    prompt, attachments = build_prompt(
        "Test instructions", 
        "simple", 
        ["/Users/luka/src/cc/mcp-second-brain/README.md"], 
        model="gpt-4.1"
    )
    print(f"   Built prompt in {time.time() - start:.3f}s")
    print(f"   Prompt length: {len(prompt)} chars")
    print(f"   Attachments: {len(attachments)} files")
    
    # Test with small file
    print("\n2. Testing prompt building with pyproject.toml:")
    start = time.time()
    prompt, attachments = build_prompt(
        "Test instructions", 
        "simple", 
        ["/Users/luka/src/cc/mcp-second-brain/pyproject.toml"], 
        model="gpt-4.1"
    )
    print(f"   Built prompt in {time.time() - start:.3f}s")
    print(f"   Prompt length: {len(prompt)} chars")
    print(f"   Attachments: {len(attachments)} files")
    
    # Test with all files
    print("\n3. Testing prompt building with all files:")
    start = time.time()
    prompt, attachments = build_prompt(
        "Test instructions", 
        "simple", 
        ["/Users/luka/src/cc/mcp-second-brain"], 
        model="gpt-4.1"
    )
    print(f"   Built prompt in {time.time() - start:.3f}s")
    print(f"   Prompt length: {len(prompt)} chars")
    print(f"   Attachments: {len(attachments)} files")
    
    return prompt

def test_individual_file_processing():
    """Test processing individual files to find the problematic one."""
    print("\n=== Testing individual file processing ===")
    
    files = gather_file_paths(["/Users/luka/src/cc/mcp-second-brain"])
    
    for i, file_path in enumerate(files[:10]):  # Test first 10 files
        print(f"\n{i+1}. Testing file: {file_path}")
        try:
            start = time.time()
            prompt, attachments = build_prompt(
                "Test", 
                "simple", 
                [file_path], 
                model="gpt-4.1"
            )
            elapsed = time.time() - start
            print(f"   ✅ Processed in {elapsed:.3f}s (prompt: {len(prompt)} chars)")
            
            # If it takes more than 1 second, that's suspicious
            if elapsed > 1.0:
                print(f"   ⚠️  WARNING: Slow processing! {elapsed:.3f}s")
                
        except Exception as e:
            print(f"   ❌ ERROR: {e}")

if __name__ == "__main__":
    print("Starting context debugging...")
    
    try:
        # Step 1: Test file gathering
        files = test_file_gathering()
        
        # Step 2: Test prompt building
        test_prompt_building(files)
        
        # Step 3: Test individual files
        test_individual_file_processing()
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()