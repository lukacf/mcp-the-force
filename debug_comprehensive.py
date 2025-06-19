#!/usr/bin/env python3
"""
Comprehensive debug script to test different models, character issues, and edge cases.
"""

import sys
import time
import os
from pathlib import Path

# Add the project to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_second_brain.utils.prompt_builder import build_prompt
from mcp_second_brain.adapters.openai_adapter import OpenAIAdapter
from mcp_second_brain.adapters.vertex_adapter import VertexAdapter

def setup_vertex():
    """Setup Vertex AI if possible."""
    # Check if we have a .env file
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        print("Found .env file, loading...")
        from dotenv import load_dotenv
        load_dotenv(env_file)
    else:
        print("No .env file found, setting test values...")
        os.environ["VERTEX_PROJECT"] = "test-project"
        os.environ["VERTEX_LOCATION"] = "us-central1"

def test_character_detection_bug():
    """Test the character detection inconsistency."""
    print("=== Testing Character Detection Bug ===")
    
    # Generate prompts and test character detection multiple times
    for i in range(3):
        print(f"\nTest {i+1}:")
        prompt, _ = build_prompt(
            "Test", 
            "simple", 
            ["/Users/luka/src/cc/mcp-second-brain"], 
            model="gpt-4.1"
        )
        
        has_null = '\x00' in prompt
        control_chars = [c for c in prompt if ord(c) < 32 and c not in '\t\n\r']
        has_control = bool(control_chars)
        
        print(f"   Prompt length: {len(prompt)}")
        print(f"   Has NULL: {has_null}")
        print(f"   Has control chars: {has_control} ({len(control_chars)} found)")
        
        # Save to file and re-read to see if there's an encoding issue
        with open(f"/tmp/test_prompt_{i}.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
        
        with open(f"/tmp/test_prompt_{i}.txt", "r", encoding="utf-8") as f:
            reread = f.read()
        
        reread_has_null = '\x00' in reread
        reread_control_chars = [c for c in reread if ord(c) < 32 and c not in '\t\n\r']
        reread_has_control = bool(reread_control_chars)
        
        print(f"   After file I/O - Has NULL: {reread_has_null}, Has control: {reread_has_control}")
        print(f"   Length changed: {len(prompt) != len(reread)}")

def test_different_models():
    """Test different OpenAI models."""
    print("\n=== Testing Different OpenAI Models ===")
    
    test_prompt = "Say 'test successful'"
    
    models = ["gpt-4.1", "o3", "o3-pro"]
    
    for model in models:
        print(f"\nTesting {model}:")
        try:
            adapter = OpenAIAdapter(model)
            start = time.time()
            response = adapter.generate(test_prompt)
            elapsed = time.time() - start
            print(f"   ✅ Response in {elapsed:.3f}s: {response[:50]}...")
        except Exception as e:
            print(f"   ❌ Error: {e}")

def test_vertex_models():
    """Test Vertex AI models."""
    print("\n=== Testing Vertex AI Models ===")
    
    setup_vertex()
    
    test_prompt = "Say 'test successful'"
    
    models = ["gemini-2.5-pro", "gemini-2.5-flash"]
    
    for model in models:
        print(f"\nTesting {model}:")
        try:
            adapter = VertexAdapter(model)
            start = time.time()
            response = adapter.generate(test_prompt)
            elapsed = time.time() - start
            print(f"   ✅ Response in {elapsed:.3f}s: {response[:50]}...")
        except Exception as e:
            print(f"   ❌ Error: {e}")

def test_context_sizes():
    """Test different context sizes to find threshold."""
    print("\n=== Testing Different Context Sizes ===")
    
    adapter = OpenAIAdapter("gpt-4.1")
    
    # Test different file combinations
    test_cases = [
        ("Single small file", ["/Users/luka/src/cc/mcp-second-brain/pyproject.toml"]),
        ("Two small files", ["/Users/luka/src/cc/mcp-second-brain/pyproject.toml", "/Users/luka/src/cc/mcp-second-brain/.env.example"]),
        ("README only", ["/Users/luka/src/cc/mcp-second-brain/README.md"]),
        ("README + small file", ["/Users/luka/src/cc/mcp-second-brain/README.md", "/Users/luka/src/cc/mcp-second-brain/pyproject.toml"]),
        ("All files", ["/Users/luka/src/cc/mcp-second-brain"]),
    ]
    
    for name, files in test_cases:
        print(f"\n{name}:")
        try:
            # Build prompt
            prompt, attachments = build_prompt("Say OK", "simple", files, model="gpt-4.1")
            print(f"   Prompt built: {len(prompt)} chars, {len(attachments)} attachments")
            
            # Test API call
            start = time.time()
            response = adapter.generate(prompt)
            elapsed = time.time() - start
            print(f"   ✅ API call: {elapsed:.3f}s - {response[:30]}...")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")

def test_prompt_variations():
    """Test if specific prompt content causes issues."""
    print("\n=== Testing Prompt Variations ===")
    
    adapter = OpenAIAdapter("gpt-4.1")
    
    # Get the full repo prompt
    full_prompt, _ = build_prompt("Say OK", "simple", ["/Users/luka/src/cc/mcp-second-brain"], model="gpt-4.1")
    
    test_cases = [
        ("Short test prompt", "Say hello"),
        ("Medium prompt", "This is a test prompt. " * 100),
        ("Long random text", "Random text. " * 1000),
        ("Full repo prompt (first 1000 chars)", full_prompt[:1000]),
        ("Full repo prompt (first 5000 chars)", full_prompt[:5000]),
        ("Full repo prompt (complete)", full_prompt),
    ]
    
    for name, prompt in test_cases:
        print(f"\n{name} ({len(prompt)} chars):")
        try:
            start = time.time()
            response = adapter.generate(prompt)
            elapsed = time.time() - start
            print(f"   ✅ Response in {elapsed:.3f}s: {response[:30]}...")
            
            if elapsed > 5.0:
                print(f"   ⚠️  SLOW RESPONSE: {elapsed:.3f}s")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    print("Starting comprehensive debugging...")
    
    try:
        test_character_detection_bug()
        test_different_models()
        test_vertex_models()
        test_context_sizes()
        test_prompt_variations()
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()