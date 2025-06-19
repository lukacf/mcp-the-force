#!/usr/bin/env python3
"""
Debug script to test API calls directly.
"""

import sys
import time
from pathlib import Path

# Add the project to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_second_brain.utils.prompt_builder import build_prompt
from mcp_second_brain.adapters.openai_adapter import OpenAIAdapter
from mcp_second_brain.adapters.vertex_adapter import VertexAdapter

def test_openai_api():
    """Test OpenAI API directly."""
    print("=== Testing OpenAI API ===")
    
    try:
        adapter = OpenAIAdapter("gpt-4.1")
        
        # Test 1: Simple prompt
        print("\n1. Testing simple prompt:")
        simple_prompt = "Say 'Hello World'"
        start = time.time()
        response = adapter.generate(simple_prompt)
        elapsed = time.time() - start
        print(f"   ✅ Response in {elapsed:.3f}s: {response[:100]}...")
        
        # Test 2: Small context
        print("\n2. Testing with README context:")
        prompt, _ = build_prompt("Say OK", "simple", ["/Users/luka/src/cc/mcp-second-brain/README.md"], model="gpt-4.1")
        start = time.time()
        response = adapter.generate(prompt)
        elapsed = time.time() - start
        print(f"   Response in {elapsed:.3f}s: {response[:100]}...")
        
    except Exception as e:
        print(f"   ❌ OpenAI Error: {e}")
        import traceback
        traceback.print_exc()

def test_vertex_api():
    """Test Vertex AI API directly."""
    print("\n=== Testing Vertex AI API ===")
    
    try:
        adapter = VertexAdapter("gemini-2.5-flash")
        
        # Test 1: Simple prompt
        print("\n1. Testing simple prompt:")
        simple_prompt = "Say 'Hello World'"
        start = time.time()
        response = adapter.generate(simple_prompt)
        elapsed = time.time() - start
        print(f"   ✅ Response in {elapsed:.3f}s: {response[:100]}...")
        
        # Test 2: Small context
        print("\n2. Testing with README context:")
        prompt, _ = build_prompt("Say OK", "simple", ["/Users/luka/src/cc/mcp-second-brain/README.md"], model="gemini-2.5-flash")
        start = time.time()
        response = adapter.generate(prompt)
        elapsed = time.time() - start
        print(f"   Response in {elapsed:.3f}s: {response[:100]}...")
        
    except Exception as e:
        print(f"   ❌ Vertex Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting API debugging...")
    
    try:
        # Test OpenAI
        test_openai_api()
        
        # Test Vertex  
        test_vertex_api()
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()