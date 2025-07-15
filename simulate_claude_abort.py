#!/usr/bin/env python3
"""
Simulate what Claude Code does when a user aborts:
1. Start an MCP call
2. After some delay, just stop reading stdout
"""

import asyncio
import json
import sys
import time
from datetime import datetime

async def simulate_claude_client():
    """Simulate Claude Code making an MCP call and then abandoning it."""
    
    print("=== Simulating Claude Code Client ===")
    
    # Start the MCP server as a subprocess
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "trace_cancellation.py",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    print(f"Started MCP server with PID {proc.pid}")
    
    # Send initialization
    init_request = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {}
        },
        "id": 1
    }
    
    proc.stdin.write((json.dumps(init_request) + "\n").encode())
    await proc.stdin.drain()
    
    # Read initialization response
    response = await proc.stdout.readline()
    print(f"Got init response: {response.decode().strip()}")
    
    # Make a tool call that will take time
    tool_call = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "chat_with_gemini25_flash",
            "arguments": {
                "instructions": "Count to 100 slowly and explain each number",
                "output_format": "Detailed explanation",
                "context": [],
                "session_id": "abort-test-001"
            }
        },
        "id": 2
    }
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Sending tool call...")
    proc.stdin.write((json.dumps(tool_call) + "\n").encode())
    await proc.stdin.drain()
    
    # Wait 14 seconds (the observed delay)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting 14 seconds before 'aborting'...")
    await asyncio.sleep(14)
    
    # SIMULATE ABORT: Just stop reading and close stdin
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] SIMULATING USER ABORT")
    print("- Closing stdin (Claude stops sending)")
    proc.stdin.close()
    
    print("- Stopping stdout read (Claude stops listening)")
    # In reality, Claude just stops reading stdout
    # We can't perfectly simulate this, but we can kill our reader task
    
    # Wait a bit to see what happens
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting to observe server behavior...")
    await asyncio.sleep(5)
    
    # Check if server is still running
    if proc.returncode is None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Server still running (PID {proc.pid})")
        print("Terminating server...")
        proc.terminate()
        await proc.wait()
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Server exited with code {proc.returncode}")
    
    # Print any stderr
    stderr = await proc.stderr.read()
    if stderr:
        print("\nServer stderr:")
        print(stderr.decode())

if __name__ == "__main__":
    asyncio.run(simulate_claude_client())