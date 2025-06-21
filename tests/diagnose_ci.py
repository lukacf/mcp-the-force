#!/usr/bin/env python3
"""Diagnostic script to understand CI environment differences."""
import os
import sys
import subprocess

def run_diagnostic():
    """Run diagnostics to understand environment differences."""
    print("=== CI Diagnostic Report ===")
    print(f"Python version: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Environment variables:")
    for key in sorted(os.environ):
        if any(x in key for x in ["MCP", "PYTEST", "PYTHON", "PATH"]):
            print(f"  {key}={os.environ[key]}")
    
    print("\nPython path:")
    for path in sys.path:
        print(f"  {path}")
    
    print("\nChecking module imports:")
    # Try importing in isolation
    env = os.environ.copy()
    env["MCP_ADAPTER_MOCK"] = "1"
    
    # Test 1: Check if env var is visible in subprocess
    result = subprocess.run(
        [sys.executable, "-c", "import os; print('MCP_ADAPTER_MOCK =', os.getenv('MCP_ADAPTER_MOCK'))"],
        env=env,
        capture_output=True,
        text=True
    )
    print(f"\nSubprocess env check: {result.stdout.strip()}")
    
    # Test 2: Check adapter registration
    result = subprocess.run(
        [sys.executable, "-c", """
import os
print('Before import, MCP_ADAPTER_MOCK =', os.getenv('MCP_ADAPTER_MOCK'))
from mcp_second_brain.adapters import ADAPTER_REGISTRY
print('Adapter types:', {k: v.__name__ for k, v in ADAPTER_REGISTRY.items()})
"""],
        env=env,
        capture_output=True,
        text=True
    )
    print(f"\nAdapter registration check:")
    print(result.stdout)
    if result.stderr:
        print(f"Errors: {result.stderr}")
    
    # Test 3: Run pytest collection
    print("\nPytest collection test:")
    result = subprocess.run(
        ["pytest", "--collect-only", "tests/integration_mcp/test_basic_mcp.py", "-v"],
        env=env,
        capture_output=True,
        text=True
    )
    print(f"Exit code: {result.returncode}")
    if "mcp_server" in result.stdout:
        print("✓ Found mcp_server fixture references")
    else:
        print("✗ No mcp_server fixture references found")
    
    if result.stderr and "fixture 'mcp_server' not found" in result.stderr:
        print("✗ ERROR: mcp_server fixture not found!")
    
    print("\nPytest output (first 1000 chars):")
    print(result.stdout[:1000])
    if result.stderr:
        print("\nPytest errors (first 1000 chars):")
        print(result.stderr[:1000])

if __name__ == "__main__":
    run_diagnostic()