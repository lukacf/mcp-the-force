#!/usr/bin/env python3
"""
Simulate EXACTLY what Claude Code does:
1. Spawn mcp-second-brain as a subprocess
2. Communicate via stdio
3. After 14 seconds, just stop reading (abandon the connection)
"""

import asyncio
import json
import sys
import os
import time
from datetime import datetime

# Enable debug logging
os.environ["MCP_DEBUG"] = "1"
os.environ["DEBUG"] = "1"

async def simulate_claude_abort():
    """Simulate Claude Code's exact behavior when user aborts."""
    
    print("=== Simulating Claude Code Abort Behavior ===")
    print(f"Working directory: {os.getcwd()}")
    
    # Start the MCP server EXACTLY as Claude does
    cmd = [sys.executable, "-m", "mcp_second_brain.server"]
    print(f"Starting MCP server: {' '.join(cmd)}")
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd()  # Use current directory
    )
    
    print(f"Started MCP server with PID {proc.pid}")
    
    # Monitor stderr in background
    async def stderr_reader():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            print(f"[STDERR] {line.decode().rstrip()}")
    
    stderr_task = asyncio.create_task(stderr_reader())
    
    try:
        # Send initialization request
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "claude-test",
                    "version": "1.0.0"
                }
            },
            "id": 1
        }
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Sending initialize request...")
        proc.stdin.write((json.dumps(init_request) + "\n").encode())
        await proc.stdin.drain()
        
        # Read response
        response = await proc.stdout.readline()
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Got response: {response.decode().strip()[:100]}...")
        
        # Send initialized notification (Claude does this)
        initialized_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Sending initialized notification...")
        proc.stdin.write((json.dumps(initialized_notif) + "\n").encode())
        await proc.stdin.drain()
        
        # Give server a moment to process
        await asyncio.sleep(0.5)
        
        # Now make a long-running tool call
        # Use a model that takes longer to ensure we abort during execution
        tool_call = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "chat_with_o3",  # Use o3 which takes longer
                "arguments": {
                    "instructions": "Write a comprehensive analysis of the P vs NP problem, exploring all major approaches to solving it, current research directions, and implications if P=NP or P≠NP. Include mathematical proofs where relevant.",
                    "output_format": "Detailed technical analysis with mathematical rigor",
                    "context": [],
                    "session_id": "abort-test-" + str(int(time.time())),
                    "reasoning_effort": "high"  # Make it think longer
                }
            },
            "id": 2
        }
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Making long-running tool call...")
        proc.stdin.write((json.dumps(tool_call) + "\n").encode())
        await proc.stdin.drain()
        
        # Start reading response in background
        async def response_reader():
            try:
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    print(f"[RESPONSE] {line.decode().rstrip()[:100]}...")
            except asyncio.CancelledError:
                print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Response reader cancelled")
                raise
        
        response_task = asyncio.create_task(response_reader())
        
        # Wait exactly 14 seconds
        print(f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Waiting 14 seconds before simulating abort...")
        await asyncio.sleep(14)
        
        # SIMULATE ABORT: This is what Claude does
        print(f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] === SIMULATING CLAUDE ABORT ===")
        print("1. Cancelling response reader (Claude stops processing output)")
        response_task.cancel()
        
        print("2. Closing stdin (Claude stops sending)")
        proc.stdin.close()
        
        print("3. NOT sending any cancel signal (Claude doesn't)")
        print("4. Just abandoning the connection...")
        
        # Wait to see what happens to the server
        print(f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Monitoring server behavior...")
        
        # Give it 10 seconds to see what happens
        for i in range(10):
            await asyncio.sleep(1)
            if proc.returncode is not None:
                print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Server exited with code {proc.returncode}")
                break
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Server still running (PID {proc.pid})...")
        
        # Check debug logs if they exist
        print(f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Checking debug logs...")
        if os.path.exists("mcp_cancellation_debug.log"):
            with open("mcp_cancellation_debug.log", "r") as f:
                print("\n=== Cancellation Debug Log ===")
                print(f.read())
        
        if os.path.exists("mcp_debug_trace.log"):
            with open("mcp_debug_trace.log", "r") as f:
                print("\n=== Debug Trace Log ===")
                print(f.read())
        
    finally:
        # Clean up
        if proc.returncode is None:
            print(f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Terminating server...")
            proc.terminate()
            await proc.wait()
        
        stderr_task.cancel()
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    # Clear debug logs
    for logfile in ["mcp_cancellation_debug.log", "mcp_debug_trace.log"]:
        if os.path.exists(logfile):
            os.remove(logfile)
    
    asyncio.run(simulate_claude_abort())