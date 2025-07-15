#!/usr/bin/env python3
"""
Test what happens when we send another command after aborting.
This simulates Claude trying to use the MCP server after an abort.
"""

import asyncio
import json
import sys
import os
import time
from datetime import datetime

async def test_post_abort():
    """Test sending commands after abort."""
    
    print("=== Testing Post-Abort Command Handling ===")
    
    # Start MCP server
    cmd = [sys.executable, "-m", "mcp_second_brain.server"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd()
    )
    
    print(f"Started MCP server with PID {proc.pid}")
    
    # stderr reader
    async def stderr_reader():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            print(f"[STDERR] {line.decode().rstrip()}")
    
    stderr_task = asyncio.create_task(stderr_reader())
    
    try:
        # Initialize
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {}
            },
            "id": 1
        }
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Sending initialize...")
        proc.stdin.write((json.dumps(init_request) + "\n").encode())
        await proc.stdin.drain()
        
        response = await proc.stdout.readline()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Init response received")
        
        # Send initialized
        proc.stdin.write((json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }) + "\n").encode())
        await proc.stdin.drain()
        
        await asyncio.sleep(0.5)
        
        # Make o3 call
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Making o3 call...")
        tool_call = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "chat_with_o3",
                "arguments": {
                    "instructions": "Count to 10 slowly",
                    "output_format": "Simple list",
                    "context": [],
                    "session_id": "test-abort"
                }
            },
            "id": 2
        }
        
        proc.stdin.write((json.dumps(tool_call) + "\n").encode())
        await proc.stdin.drain()
        
        # Start reading responses
        response_lines = []
        async def response_reader():
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                response_lines.append(line)
                print(f"[RESPONSE] {line.decode().rstrip()[:80]}...")
        
        response_task = asyncio.create_task(response_reader())
        
        # Wait 14 seconds
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Waiting 14 seconds...")
        await asyncio.sleep(14)
        
        # SIMULATE ABORT
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === SIMULATING ABORT ===")
        response_task.cancel()
        try:
            await response_task
        except asyncio.CancelledError:
            pass
        
        # DON'T close stdin - Claude might still try to send commands
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Response reader cancelled (Claude stops listening)")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] But stdin still open (Claude might send more)")
        
        # Wait a bit
        await asyncio.sleep(2)
        
        # NOW TRY TO SEND ANOTHER COMMAND
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === ATTEMPTING POST-ABORT COMMAND ===")
        
        # Try a simple tool list request
        list_tools = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 3
        }
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sending tools/list request...")
        try:
            proc.stdin.write((json.dumps(list_tools) + "\n").encode())
            await proc.stdin.drain()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Request sent successfully")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to send: {type(e).__name__}: {e}")
        
        # Try to read response with timeout
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting for response...")
        try:
            response = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Got response: {response.decode().strip()[:100]}")
        except asyncio.TimeoutError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No response after 5 seconds - server may be frozen")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Read failed: {type(e).__name__}: {e}")
        
        # Try another command - maybe a simpler one
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Trying a simpler command...")
        ping = {
            "jsonrpc": "2.0",
            "method": "ping",
            "params": {},
            "id": 4
        }
        
        try:
            proc.stdin.write((json.dumps(ping) + "\n").encode())
            await proc.stdin.drain()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ping sent")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to send ping: {e}")
        
        # Check if process is still alive
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking server status...")
        if proc.returncode is None:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Server still running (PID {proc.pid})")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Server exited with code {proc.returncode}")
        
        # Check debug logs
        if os.path.exists("mcp_cancellation_debug.log"):
            print("\n=== Recent Debug Log Entries ===")
            with open("mcp_cancellation_debug.log", "r") as f:
                lines = f.readlines()
                for line in lines[-20:]:  # Last 20 lines
                    print(line.rstrip())
        
    finally:
        # Cleanup
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()
        
        stderr_task.cancel()
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    # Clear logs
    for f in ["mcp_cancellation_debug.log", "mcp_debug_trace.log"]:
        if os.path.exists(f):
            os.remove(f)
    
    asyncio.run(test_post_abort())