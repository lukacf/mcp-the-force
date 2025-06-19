#!/usr/bin/env python3
"""
Debug script to inspect the actual content being generated.
"""

import sys
import time
from pathlib import Path

# Add the project to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_second_brain.utils.prompt_builder import build_prompt

def inspect_prompt_content():
    """Inspect what's actually in the generated prompts."""
    print("=== Inspecting Prompt Content ===")
    
    # Test 1: Single file that works (README.md)
    print("\n1. README.md prompt content:")
    prompt, attachments = build_prompt(
        "Say OK", 
        "simple", 
        ["/Users/luka/src/cc/mcp-second-brain/README.md"], 
        model="gpt-4.1"
    )
    print(f"   Prompt length: {len(prompt)} chars")
    print(f"   First 500 chars:")
    print(f"   {repr(prompt[:500])}")
    print(f"   Last 500 chars:")
    print(f"   {repr(prompt[-500:])}")
    
    # Test 2: Single file that hangs (pyproject.toml)
    print("\n2. pyproject.toml prompt content:")
    prompt, attachments = build_prompt(
        "Say OK", 
        "simple", 
        ["/Users/luka/src/cc/mcp-second-brain/pyproject.toml"], 
        model="gpt-4.1"
    )
    print(f"   Prompt length: {len(prompt)} chars")
    print(f"   Full content:")
    print(f"   {repr(prompt)}")
    
    # Test 3: Full directory
    print("\n3. Full directory prompt content (first 1000 chars):")
    prompt, attachments = build_prompt(
        "Say OK", 
        "simple", 
        ["/Users/luka/src/cc/mcp-second-brain"], 
        model="gpt-4.1"
    )
    print(f"   Prompt length: {len(prompt)} chars")
    print(f"   First 1000 chars:")
    print(f"   {repr(prompt[:1000])}")
    
    # Check for problematic characters
    print(f"\n4. Character analysis of full prompt:")
    has_null = '\x00' in prompt
    control_chars = [c for c in prompt if ord(c) < 32 and c not in '\t\n\r']
    has_control = bool(control_chars)
    
    print(f"   Contains NULL bytes: {has_null}")
    print(f"   Contains other control chars: {has_control}")
    print(f"   Total control chars found: {len(control_chars)}")
    
    if control_chars:
        print(f"   Control characters found: {set(repr(c) for c in control_chars[:10])}")
        # Show positions of first few control chars
        for i, c in enumerate(prompt):
            if ord(c) < 32 and c not in '\t\n\r':
                start = max(0, i - 20)
                end = min(len(prompt), i + 20)
                print(f"   Control char {repr(c)} at position {i}: {repr(prompt[start:end])}")
                break
    
    return prompt

if __name__ == "__main__":
    print("Starting content inspection...")
    
    try:
        prompt = inspect_prompt_content()
        
        # Save the full prompt for manual inspection if needed
        with open("/tmp/debug_prompt.txt", "w", encoding="utf-8", errors="replace") as f:
            f.write(prompt)
        print(f"\nFull prompt saved to /tmp/debug_prompt.txt")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()